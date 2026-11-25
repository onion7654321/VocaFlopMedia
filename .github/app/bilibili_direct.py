"""Direct public Bilibili DASH downloader. No yt-dlp dependency.

Only downloads content exposed to the current session; it does not bypass access controls.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from http.cookiejar import MozillaCookieJar

API = 'https://api.bilibili.com'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/', 'Accept': 'application/json, text/plain, */*'
}
MIXIN = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]

class BiliError(RuntimeError):
    pass

def _opener(settings=None):
    handlers = []
    cookie_file = str((settings or {}).get('cookies_file') or '')
    if cookie_file and Path(cookie_file).is_file():
        jar = MozillaCookieJar(cookie_file)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            handlers.append(urllib.request.HTTPCookieProcessor(jar))
        except Exception as e:
            raise BiliError(f'Cannot read cookies.txt: {e}') from e
    return urllib.request.build_opener(*handlers)

def _get_json(url, opener):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with opener.open(req, timeout=25) as response:
            payload = json.load(response)
    except Exception as e:
        raise BiliError(f'Bilibili request failed: {e}') from e
    if int(payload.get('code', 0)) != 0:
        raise BiliError(f'Bilibili API {payload.get("code")}: {payload.get("message") or "Unavailable"}. Try a public video or an authorized cookies.txt.')
    return payload.get('data') or {}

def _extract_bvid(url, opener):
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname in {'b23.tv', 'www.b23.tv'}:
        try:
            with opener.open(urllib.request.Request(url, headers=HEADERS), timeout=20) as resp:
                url = resp.url
        except Exception as e:
            raise BiliError(f'Cannot resolve Bilibili short link: {e}') from e
    match = re.search(r'/video/(BV[0-9A-Za-z]{10})', url, re.I)
    if not match:
        raise BiliError('Expected a Bilibili /video/BV... link.')
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        part = max(1, int(query.get('p', ['1'])[0]))
    except ValueError:
        part = 1
    return match.group(1), part

def _signed_url(bvid, cid, opener):
    nav = _get_json(API + '/x/web-interface/nav', opener)
    wbi = nav.get('wbi_img') or {}
    a = Path(urllib.parse.urlparse(wbi.get('img_url','')).path).stem
    b = Path(urllib.parse.urlparse(wbi.get('sub_url','')).path).stem
    key = ''.join((a+b)[i] for i in MIXIN if i < len(a+b))[:32]
    if not key:
        raise BiliError('Could not obtain Bilibili WBI signing key.')
    params = {'bvid':bvid, 'cid':str(cid), 'qn':'120', 'fnval':'16', 'fourk':'1', 'wts':str(int(time.time()))}
    params = {k: re.sub(r"[!'()*]", '', str(v)) for k,v in params.items()}
    query = urllib.parse.urlencode(sorted(params.items()))
    params['w_rid'] = hashlib.md5((query+key).encode()).hexdigest()
    return API + '/x/player/wbi/playurl?' + urllib.parse.urlencode(params)

def _streams(url, settings):
    opener = _opener(settings)
    bvid, part = _extract_bvid(url, opener)
    meta = _get_json(API + '/x/web-interface/view?bvid=' + urllib.parse.quote(bvid), opener)
    pages = meta.get('pages') or []
    if part > len(pages):
        raise BiliError(f'This video has only {len(pages)} part(s); requested part {part}.')
    cid = pages[part-1]['cid']
    stream = _get_json(_signed_url(bvid, cid, opener), opener)
    dash = stream.get('dash') or {}
    videos = dash.get('video') or []
    audios = dash.get('audio') or []
    if not videos or not audios:
        raise BiliError('No accessible DASH video/audio streams. This video may require Bilibili login or membership.')
    return meta, videos, audios, opener

def _stream_url(item):
    return item.get('baseUrl') or item.get('base_url') or (item.get('backupUrl') or item.get('backup_url') or [''])[0]

def _select_video(videos, requested_height):
    # height can be absent in API variants. Explicitly favor avc1, then available bandwidth.
    allowed = [v for v in videos if not requested_height or int(v.get('height') or 0) <= requested_height]
    if not allowed:
        allowed = videos
    return max(allowed, key=lambda v: (int(v.get('height') or 0), str(v.get('codecs') or '').startswith('avc1'), int(v.get('bandwidth') or 0)))

def _fetch_file(url, path, opener, progress, cancel_event, max_bytes, base, portion):
    if not url.startswith('https://'):
        raise BiliError('Unsafe or invalid media stream URL.')
    req = urllib.request.Request(url, headers={**HEADERS, 'Accept':'*/*'})
    total = 0
    try:
        with opener.open(req, timeout=45) as resp, open(path,'wb') as out:
            length = int(resp.headers.get('Content-Length') or 0)
            if max_bytes and length > max_bytes:
                raise BiliError('Stream exceeds configured size limit.')
            while True:
                if cancel_event.is_set():
                    raise BiliError('Cancelled')
                chunk = resp.read(256*1024)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    raise BiliError('Stream exceeds configured size limit.')
                out.write(chunk)
                if length:
                    progress(min(.94,base + portion * total/length), 'Downloading Bilibili...')
    except BiliError:
        raise
    except Exception as e:
        raise BiliError(f'Bilibili CDN download failed: {e}') from e
    if total < 1024:
        raise BiliError('Bilibili returned an empty or invalid media stream.')

def _safe_filename(title):
    return (re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title).strip(' .')[:140] or 'Bilibili')

def _run_download(job, settings, progress, cancel_event):
    from .toolchain import resolve_tool
    meta, videos, audios, opener = _streams(job.url, settings)
    ffmpeg = resolve_tool('ffmpeg', settings)
    if not ffmpeg:
        raise BiliError('FFmpeg not found. Set its location in Settings.')
    ffprobe = resolve_tool('ffprobe', settings)
    if not ffprobe:
        raise BiliError('FFprobe not found. Place ffprobe.exe next to ffmpeg.exe.')
    folder = Path(job.folder)
    folder.mkdir(parents=True, exist_ok=True)
    title = _safe_filename(str(meta.get('title') or 'Bilibili'))
    filename = folder / f'{title} [{meta.get("bvid", "video")}].{job.kind}'
    if filename.exists():
        return {'status':'Completed','files':[str(filename)],'error':'','log':'File already exists.'}
    max_bytes = max(0,int(settings.get('max_size_mb',0))) * 1024 * 1024
    audio = max(audios, key=lambda a: int(a.get('bandwidth') or 0))
    with tempfile.TemporaryDirectory(prefix='vocaflop_bili_') as temp:
        temp = Path(temp)
        a_path = temp/'audio.m4s'
        if job.kind == 'mp4':
            video = _select_video(videos, int(job.quality or 0))
            v_path = temp/'video.m4s'
            _fetch_file(_stream_url(video),v_path,opener,progress,cancel_event,max_bytes,0,.53)
            remaining = max_bytes-v_path.stat().st_size if max_bytes else 0
            if max_bytes and remaining <= 0:
                raise BiliError('Video alone exceeds size limit.')
            _fetch_file(_stream_url(audio),a_path,opener,progress,cancel_event,remaining,.53,.37)
            inputs = ['-i',str(v_path),'-i',str(a_path)]
            options = ['-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k']
        else:
            _fetch_file(_stream_url(audio),a_path,opener,progress,cancel_event,max_bytes,0,.9)
            inputs = ['-i',str(a_path)]
            options = ['-vn','-codec:a','libmp3lame','-b:a',f'{int(job.quality or 192)}k']
        if cancel_event.is_set():
            raise BiliError('Cancelled')
        section = []
        if job.start is not None:
            section += ['-ss',str(job.start)]
        if job.end is not None:
            section += ['-to',str(job.end)]
        tmp_out = temp/('result.'+job.kind)
        cmd = [str(ffmpeg),'-hide_banner','-loglevel','error','-y',*inputs,*section,*options,str(tmp_out)]
        finished = subprocess.run(cmd,capture_output=True,text=True,timeout=3600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if finished.returncode or not tmp_out.exists() or tmp_out.stat().st_size < 1024:
            raise BiliError('FFmpeg merge failed: ' + (finished.stderr or 'Output missing')[-650:])
        check = subprocess.run([str(ffprobe),'-v','error','-show_entries','format=duration','-of','json',str(tmp_out)],capture_output=True,text=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if check.returncode:
            raise BiliError('FFprobe could not validate the merged media.')
        if max_bytes and tmp_out.stat().st_size > max_bytes:
            raise BiliError('Final file exceeds configured size limit.')
        __import__('shutil').move(str(tmp_out),str(filename))
        progress(1.,'Completed')
    return {'status':'Completed','files':[str(filename)],'error':'','log':'Direct Bilibili API + FFmpeg (no yt-dlp).'}

def _run_probe(url, settings):
    meta, videos, audios, _ = _streams(url, settings)
    heights = sorted({int(v.get('height') or 0) for v in videos if int(v.get('height') or 0) > 0},reverse=True)[:4]
    return {'title':meta.get('title') or 'Bilibili video', 'thumbnail':meta.get('pic') or '',
            'channel':(meta.get('owner') or {}).get('name') or '',
            'duration':meta.get('duration'), 'resolutions':heights or [0],
            'is_live':False, 'playback_url':''}

async def probe(url, settings):
    return await asyncio.to_thread(_run_probe,url,settings)

async def download(job,settings,on_progress,cancel_event):
    try:
        return await asyncio.to_thread(_run_download,job,settings,on_progress,cancel_event)
    except BiliError as e:
        return {'status':'Cancelled' if str(e)=='Cancelled' else 'Failed', 'files':[], 'error':str(e), 'log':str(e)}
