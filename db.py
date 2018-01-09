import sqlite3
from pathlib import Path
from moment import Moment, unix
from shutil import rmtree
from datetime import datetime

def params(path):
    try:
        path = Path(path)
        conn = sqlite3.connect(str(path / '.sync.db'))
        c = conn.cursor()
        c.execute('SELECT server_url, remote_path, username, password FROM params')
        r = c.fetchone()
        return r[0], r[1], r[2], r[3]
    finally:
        conn.close()
    return None

# Sqlite3 doesn't support full outer join or right joins, so this emulates
# a full outer join between the three tables by using three left joins and
# selecting only rows that haven't been returned by a previous query.
sync_query = '''
select sync.file_path as fp, sync.is_folder, sync.last_sync,
       sp.is_folder, sp.tstamp,
       fs.is_folder, fs.tstamp
from sync
left join sp using(file_path)
left join fs using(file_path)
where sync.file_path is not null

union all

select sp.file_path as fp, sync.is_folder, sync.last_sync,
       sp.is_folder, sp.tstamp,
       fs.is_folder, fs.tstamp
from sp
left join sync using(file_path)
left join fs using(file_path)
where sync.file_path is null
and sp.file_path is not null

union all

select fs.file_path as fp, sync.is_folder, sync.last_sync,
       sp.is_folder, sp.tstamp,
       fs.is_folder, fs.tstamp
from fs
left join sp using(file_path)
left join sync using(file_path)
where sync.file_path is null and sp.file_path is null
and fs.file_path is not null
;
'''

class DB():
    def __init__(self, path, sp_f, dry_run):
        self.dry_run = dry_run
        self.path = Path(path)
        self.db_path = self.path / '.sync.db'
        self.sp_f = sp_f
        if not self.path.exists():
            self.path.mkdir(parents=True)
        if not self.db_path.exists():
            self.conn = sqlite3.connect(str(self.db_path))
            c = self.conn.cursor()
            c.execute('''CREATE TABLE params (
                server_url text,
                remote_path text,
                username text,
                password text
            )''')
            c.execute('''INSERT INTO params (server_url, remote_path, username, password) VALUES (?, ?, ?, ?)''',
                        (str(sp_f.sp.site_url), str(sp_f.path), sp_f.sp.username, sp_f.sp.password))
            c.execute('''CREATE TABLE sync (
                file_path text primary key,
                is_folder boolean,
                synced boolean,
                last_sync timestamp
            )''')
            c.execute('''CREATE TABLE sp (
                file_path text primary key,
                is_folder boolean,
                tstamp timestamp
            )''')
            c.execute('''CREATE TABLE fs (
                file_path text primary key,
                is_folder boolean,
                tstamp timestamp
            )''')
            self.conn.commit()
        else:
            self.conn = sqlite3.connect(str(self.db_path))

    def from_sp(self):
        c = self.conn.cursor()
        c.execute('DELETE FROM sp')
        def log_obj(ff):
            rel_path = ff.relative_to(self.sp_f)
            c.execute('INSERT INTO sp (file_path, is_folder, tstamp) VALUES (?, ?, ?)',
                        (str(rel_path), ff.is_folder, Moment(ff.timestamp).done()))
            if ff.is_folder:
                for fff in ff:
                    log_obj(fff)
        for file in self.sp_f:
            log_obj(file)
        self.conn.commit()

    def from_fs(self):
        c = self.conn.cursor()
        c.execute('DELETE FROM fs')
        def log_file(pp):
            if pp.is_dir():
                tstamp = pp.stat().st_ctime
            else:
                tstamp = pp.stat().st_mtime
            c.execute('INSERT INTO fs(file_path, is_folder, tstamp) VALUES (?, ?, ?)',
                        (str(pp.relative_to(p.parent)), pp.is_dir(), tstamp))
            if pp.is_dir():
                for ppp in pp.iterdir():
                    log_file(ppp)
        for p in self.path.iterdir():
            if (p.relative_to(self.path) == Path('.sync.db') or
                p.relative_to(self.path) == Path('.sync.db-journal')):
                # Skip our own database files
                continue
            log_file(p)
        self.conn.commit()

    def sync_to_sp(self, row):
        print(' < + Sync to Remote: {}'.format(row[0]))
        if self.dry_run:
            return
        local_p = self.path / row[0]
        if local_p.is_dir():
            self.sp_f.sp.create_folder(self.sp_f.path / row[0])
        else:
            result = self.sp_f.sp.create_file(self.sp_f.path / row[0], local_p.open('rb'), local_p.stat().st_size)
        self.update_sync(row)

    def sync_to_fs(self, row):
        print(' > + Sync to Local: {}'.format(row[0]))
        if self.dry_run:
            return
        local_p = self.path / row[0]
        try:
            file = self.sp_f.sp.get_file(self.sp_f.path / row[0])
        except ValueError:
            file = self.sp_f.sp.get_folder(self.sp_f.path / row[0])
        download = False
        if local_p.exists():
            if local_p.is_dir():
                if file.is_folder:
                    # Both folders - do nothing
                    pass
                else:
                    rmtree(local_p)
                    download=True
            else:
                if file.is_folder:
                    local_p.unlink()
                    local_p.mkdir(parents=True)
                else:
                    download=True
        else:
            if file.is_folder:
                local_p.mkdir(parents=True)
            else:
                download=True

        if download:
            size = file.length
            with local_p.open('wb') as f:
                for chunk in file.read():
                    f.write(chunk)

        self.update_sync(row)

    def unlink_from_fs(self, row):
        print(' > - Deleted from Remote: {}'.format(row[0]))
        if self.dry_run:
            return
        local_p = self.path / row[0]
        if local_p.exists():
            if local_p.is_dir():
                rmtree(local_p)
            else:
                local_p.unlink()
        else:
            print('       Already gone')
        self.remove_from_sync(row)

    def unlink_from_sp(self, row):
        print(' < - Deleted from Local: {}'.format(row[0]))
        if self.dry_run:
            return
        try:
            if row[3]:
                file = self.sp_f.sp.get_folder(self.sp_f.path / row[0])
            else:
                file = self.sp_f.sp.get_file(self.sp_f.path / row[0])
            file.delete()
        except ValueError:
            # File already missing from remote side
            print('       Already gone')
            pass
        self.remove_from_sync(row)

    def update_sync(self, row):
        c = self.conn.cursor()
        tstamp = datetime.now()
        c.execute('''INSERT OR REPLACE INTO sync (file_path, is_folder, synced, last_sync)
                        VALUES (?, ?, ?, ?)''',
                    # The 'not not' here forces 'None' to evaluate to a real boolean value.
                    # max(x or y, y or x) will give the maximum, treating None as the minimumest
                    # possible value.
                    (row[0], row[3] or not not row[5], True, tstamp))

    def remove_from_sync(self, row):
        c = self.conn.cursor()
        c.execute('DELETE FROM sync WHERE file_path = ?', (row[0],))

    def sync(self):
        self.from_fs()
        self.from_sp()

        c = self.conn.cursor()
        c.execute(sync_query)

        for row in c.fetchall():
            sync = (row[1], Moment(row[2]).locale('UTC') if row[2] else None)
            sp = (row[3], Moment(row[4]) if row[4] else None)
            fs = (row[5], unix(row[6], utc=True) if row[6] else None)
            # Figure out which version is newest and sync that version to the other
            local_p = self.path / row[0]
#            print(row[0], sync, sp, fs)
            if sync[0] is None:
                if sp[0] is None and fs[0] is not None:
                    # The file only exists on the FS and hasn't previously been seen
                    # so sync it to the server
                    self.sync_to_sp(row)
                elif sp[0] is not None and fs[0] is None:
                    # The file only exists on the server and hasn't previously been seen.
                    # Sync it to the FS
                    self.sync_to_fs(row)
                elif sp[0] is not None and fs[0] is not None:
                    # The file has appeared on both sides since the last sync.
                    print(' *** Error: file {} conflict'.format(row[0]))
                else:
                    # The file has been deleted on both sides since the last sync.
                    print(' --- Deleted from Both: {}'.format(row[0]))
                    self.remove_from_sync(row)
            else:
                if sp[0] is None or fs[0] is None:
                    if sp[0] is not None:
                        self.unlink_from_sp(row)
                    if fs[0] is not None:
                        self.unlink_from_fs(row)
                    if sp[0] is None and fs[0] is None:
                        print(' --- Deleted from Both: {}'.format(row[0]))
                    self.remove_from_sync(row)
                else:
                    if sync[1] >= sp[1] and sync[1] >= fs[1]:
                        # Both sides are older than the last sync
                        if sp[0]:
                            print('     Up to Date Folder: {}'.format(row[0]))
                        else:
                            print('     Up to Date: {}'.format(row[0]))
                    elif sp[0] and fs[0]:
                        # Both sides are folders.  Leave them be.
                        print('     Up to Date Folder: {}'.format(row[0]))
                    elif sync[1] < sp[1] and sync[1] < fs[1]:
                        print(' *** Error: file {} conflict'.format(row[0]))
                        resp = ''
                        while len(resp) == 0 or (resp[0] != 'r' and resp[0] != 'l'):
                            resp = input('     Take [R]emote or [L]ocal? ').lower()
                        if resp[0] == 'l':
                            self.sync_to_sp(row)
                        else:
                            self.sync_to_fs(row)
                    elif sp[1] >= sync[1] and sp[1] >= fs[1]:
                        # SP version is newer
                        self.sync_to_fs(row)
                    elif fs[1] >= sync[1] and fs[1] >= sp[1]:
                        # Local version is newer
                        self.sync_to_sp(row)
        self.conn.commit()
