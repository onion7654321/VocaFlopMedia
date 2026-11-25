import unittest
from app.bilibili_direct import _extract_bvid, _select_video, _safe_filename, _stream_url, BiliError

class BilibiliDirectTests(unittest.TestCase):
    def test_bvid_and_part(self):
        self.assertEqual(_extract_bvid('https://www.bilibili.com/video/BV1xx411c7mD?p=3',None),('BV1xx411c7mD',3))
    def test_bad_url(self):
        with self.assertRaises(BiliError):
            _extract_bvid('https://www.bilibili.com/',None)
    def test_select_height(self):
        streams=[{'height':1080,'codecs':'av01','bandwidth':5000},{'height':720,'codecs':'avc1','bandwidth':3000}]
        self.assertEqual(_select_video(streams,720)['height'],720)
    def test_file_name(self):
        self.assertEqual(_safe_filename('A/B:C?'), 'A_B_C_')
    def test_backup_url(self):
        self.assertEqual(_stream_url({'backupUrl':['https://cdn.example/test']}),'https://cdn.example/test')

if __name__ == '__main__': unittest.main()
