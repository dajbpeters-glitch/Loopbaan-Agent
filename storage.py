import json, sqlite3
from datetime import datetime
from domain import normalize_vacancy
class Storage:
    def __init__(self,path='loopbaan_agent_3.db'): self.path=path
    def connect(self): return sqlite3.connect(self.path)
    def initialize(self):
        with self.connect() as c:c.executescript('''CREATE TABLE IF NOT EXISTS profiles(k TEXT PRIMARY KEY,j TEXT,t TEXT);CREATE TABLE IF NOT EXISTS strategies(k TEXT PRIMARY KEY,j TEXT,t TEXT);CREATE TABLE IF NOT EXISTS library(id TEXT PRIMARY KEY,j TEXT,status TEXT,t TEXT);CREATE TABLE IF NOT EXISTS matches(k TEXT,h TEXT,j TEXT,t TEXT,PRIMARY KEY(k,h));CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,k TEXT,vid TEXT,title TEXT,org TEXT,judgement TEXT,reason TEXT,note TEXT,t TEXT);''')
    def _save(self,table,k,j):
        with self.connect() as c:c.execute(f'INSERT OR REPLACE INTO {table}(k,j,t) VALUES(?,?,?)',(k,json.dumps(j,ensure_ascii=False),datetime.now().isoformat()))
    def _get(self,table,k):
        with self.connect() as c:r=c.execute(f'SELECT j FROM {table} WHERE k=?',(k,)).fetchone()
        return json.loads(r[0]) if r else None
    def save_profile(self,k,j):self._save('profiles',k,j)
    def get_profile(self,k):return self._get('profiles',k)
    def save_strategy(self,k,j):self._save('strategies',k,j)
    def get_strategy(self,k):return self._get('strategies',k)
    def save_vacancy(self,v,status='nieuw'):
        v=normalize_vacancy(v)
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO library(id,j,status,t) VALUES(?,?,?,?)',(v['id'],json.dumps(v,ensure_ascii=False),status,datetime.now().isoformat()))
    def get_vacancies(self):
        with self.connect() as c:rows=c.execute('SELECT j,status FROM library ORDER BY t DESC').fetchall()
        out=[]
        for j,s in rows:
            v=normalize_vacancy(json.loads(j));v['_library_status']=s;out.append(v)
        return out
    def delete_vacancy(self,i):
        with self.connect() as c:c.execute('DELETE FROM library WHERE id=?',(i,))
    def save_match(self,k,h,j):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO matches(k,h,j,t) VALUES(?,?,?,?)',(k,h,json.dumps(j,ensure_ascii=False),datetime.now().isoformat()))
    def get_match(self,k,h):
        with self.connect() as c:r=c.execute('SELECT j FROM matches WHERE k=? AND h=?',(k,h)).fetchone()
        return json.loads(r[0]) if r else None
    def add_feedback(self,k,v,judgement,reason,note):
        with self.connect() as c:c.execute('INSERT INTO feedback(k,vid,title,org,judgement,reason,note,t) VALUES(?,?,?,?,?,?,?,?)',(k,v['id'],v['title'],v['organisation'],judgement,reason,note,datetime.now().isoformat()))
    def get_feedback(self,k):
        with self.connect() as c:
            c.row_factory=sqlite3.Row;rows=c.execute('SELECT title,org as organisation,judgement,reason,note FROM feedback WHERE k=? ORDER BY id DESC LIMIT 100',(k,)).fetchall()
        return [dict(r) for r in rows]
