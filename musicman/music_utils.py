from youtube_dl import YoutubeDL

YDL_OPTIONS = {'format': 'bestaudio', 'noplaylist':'True'}


def get_audio(src: str, *args):
    kw: str = ' '.join([src, *args])
    try:
        audio_dl = YoutubeDL(YDL_OPTIONS)
        resp = audio_dl.extract_info(f'ytsearch:{kw}', download=False)['entries'][0]
        return resp
    except:
        return None