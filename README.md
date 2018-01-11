# Sharepoint Sync Tool

This tool can sync Sharepoint (and OneDrive for Business) document libraries
with local filesystems.

## Requirements
- Tested on Python 3.6.
- Should work on Python 3.4+, may work on Python 2.7.
- Requires Office365-REST-Python-Client (currently requires installation from git after commit 36dd598f416676876634cd38228b75e3323d9cc8 but this will change when the version in PyPI is updated).

## Usage

The first time you sync a site, do this:

    obsync.py -u me@myorg.com ./LocalPath 'https://mysharepoint.sharepoint.com/sites/SiteName/' 'Remote Path'

This will ask you for a password; you can also specify `--pw=MyPassword` on the
command-line if you're okay with your password ending up in your command
history.

The last parameter, the remote path, can be either:

- An absolute path such as `/sites/MySite/Shared Documents`; or
- A path relative to your site, such as `Shared Documents`.

`Shared Documents` is the usual name of the document library on a site but you
can sync whatever folder on the SharePoint site you like.

Note that the `Shared Documents` folder commonly contains a `Forms` folder which
most clients hide but this one doesn't.  Its contents are more about how
Sharepoint works than your document library.

Subsequently, you can do this:

    obsync.py ./LocalPath

though if you want to put the whole command-line again, you can.

## Notes

The tool maintains a database in `./LocalPath/.sync.db`.  Don't mess with it.

Your password is stored in plain text in the database.

### TODOs

 - The list of files on the sharepoint site is currently fetched by enumerating
   all files and folders in each directory.  This means there is one request
   for each folder in the tree.  This should be replaced with listing all the
   files in the `Documents` list on the sharepoint site and filtering for the
   root path.  Such requests have a limit of 5,000 items returned for each
   request, but it is still almost certain to involve many fewer requests.
 - Store the authentication token in the database and only request a new one
   when it doesn't work.
 - Add a command-line option to not store the password in the database and
   request it every time it's needed.
 - Sync files in parallel.

## Other bits and bobs

 - shell.py will connect to the SharePoint server but do nothing else.  Usually
   this is useful in conjunction with Python's `-i` switch, which gives you a
   Python interpreter with an object called `sp` which is the connection to
   the server.
 - tree.py lists the folders on the SharePoint server.
