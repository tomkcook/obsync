from sharepoint import SharePoint, Folder
from pathlib import Path
from argparse import ArgumentParser
from getpass import getpass
from db import DB, params

parser = ArgumentParser()
parser.add_argument('local_path')
parser.add_argument('server', nargs='?')
parser.add_argument('remote_path', nargs='?')
parser.add_argument('--username', '-u', nargs='?')
args = parser.parse_args()

args.pw = None
if not args.server:
    ps = params(args.local_path)
    if ps:
        args.server = ps[0]
        args.remote_path = ps[1]
        args.username = ps[2]
        args.pw = ps[3]
if not args.server:
    parser.print_help()
    exit()

if not args.pw:
    args.pw = getpass()

sp = SharePoint(args.server, args.username, args.pw)
