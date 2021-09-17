from youtube_dl import YoutubeDL
from youtubesearchpython import VideosSearch


def get_first_yt_link(kw: str) -> str:
    
    resp = VideosSearch(kw, limit=5).result()
    if resp and 'result' in resp and len(resp['result']) > 0:
        return resp['result'][0]['link']

    return None


def get_audio(src: str, path: str, *args):
    kw: str = ' '.join([src, *args])
    link: str = get_first_yt_link(kw)

    if link:
        audio_dl = YoutubeDL({'format': '250', 'outtmpl': f'{path}%(title)s.%(ext)s'})
        resp = audio_dl.extract_info(link)
        return f'{path}{resp["title"]}.{resp["ext"]}'

    return None