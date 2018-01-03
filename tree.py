from sharepoint import SharePoint, Folder
from pathlib import Path
from argparse import ArgumentParser
from getpass import getpass
from db import DB, params

parser = ArgumentParser()
parser.add_argument('server', nargs='?')
parser.add_argument('--username', '-u', nargs='?')
args = parser.parse_args()

args.pw = getpass()

sp = SharePoint(args.server, args.username, args.pw)
f = sp.get_folder('')
for ff in f:
    print(ff.name)
