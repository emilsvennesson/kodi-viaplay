import sys
from resources.lib.kodihelper import KodiHelper

helper = KodiHelper()

class Login:
    def __init__(self):
        if helper.get_setting('autologin'):
            helper.authorize(autologin=True)

if __name__ == '__main__':
    r = Login()