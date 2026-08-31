import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
import pandas as pd


class Query:
    def __init__(self, rows):
        self.rows, self.calls, self.bounds = rows, [], (0, 499)
    def table(self, *args, **kwargs): return self
    def select(self, *args, **kwargs): return self
    def gte(self, *args): self.calls.append(('gte', args)); return self
    def lte(self, *args): self.calls.append(('lte', args)); return self
    def like(self, *args): self.calls.append(('like', args)); return self
    def order(self, *args): self.calls.append(('order', args)); return self
    def range(self, start, end): self.bounds=(start,end); return self
    def execute(self):
        start, end = self.bounds
        # Emulate a server cap smaller than requested: loader must continue.
        return SimpleNamespace(data=self.rows[start:min(end+1,start+200)], count=len(self.rows))


def reader(client):
    tree = ast.parse(Path(__file__).with_name('database.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='read_decline_window')
    fn.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
    namespace={'pd':pd,'get_supabase':lambda:client}
    exec(compile(module,'database.py','exec'),namespace)
    return namespace['read_decline_window']


class ReaderTests(unittest.TestCase):
    def test_bounded_pagination_preserves_nulls(self):
        query = Query([dict(date='2026-08-30',ALIAS=f'M-{i}',UNIQUEID=f'M-{i}:AllLayer',OIL=None,WATER=0) for i in range(1201)])
        df=reader(query)('2026-08-30')
        self.assertEqual(len(df),1201)
        self.assertTrue(df.OIL.isna().all())
        self.assertIn(('gte',('date','2026-07-06')),query.calls)
        self.assertIn(('lte',('date','2026-08-30')),query.calls)
        self.assertIn(('like',('UNIQUEID','M-%:AllLayer')),query.calls)

    def test_incomplete_server_page_raises(self):
        query=Query([])
        query.execute=lambda:SimpleNamespace(data=[],count=3)
        with self.assertRaises(RuntimeError): reader(query)('2026-08-30')

    def test_empty_returns_schema(self):
        df=reader(Query([]))('2026-08-30')
        self.assertTrue(df.empty)
        self.assertIn('UNIQUEID',df)


if __name__=='__main__': unittest.main()

