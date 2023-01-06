import sys
from resources.lib.kodihelper import KodiHelper

class Login:
    def __init__(self):
        KodiHelper().authorize(autologin=True)

if __name__ == '__main__':
    r = Login()