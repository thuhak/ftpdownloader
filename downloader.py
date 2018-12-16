import ftplib


class FileDownloader:
    def __init__(self, host, user, password, default_regex):
        self.host = host
        self.user = user
        self.password = password
        self.default_regex = default_regex

    def __enter__(self):
        pass



