"""Offline tests of extractive search compilation and logged query generation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import generate_search_queries as Q


class SearchQueryTests(unittest.TestCase):
    def test_source_bound_compilation_and_rejections(self):
        question = "What is the role of CD2 and CD44 in diabetic nephropathy?"
        groups = {"context": ["diabetic nephropathy"], "focus": ["CD2", "CD44"]}
        self.assertEqual(Q.compile_query(groups, question), "((diabetic AND nephropathy)) AND ((CD2) OR (CD44))")
        for invalid in ({"context":["kidney disease"],"focus":["CD2"]},
                        {"context":["diabetic nephropathy"],"focus":["CD2 OR cancer"]},
                        {"context":["diabetic nephropathy"],"focus":[]},
                        {"context":["CD2"],"focus":["CD2"]}, {"needs_review":True}):
            with self.assertRaises(ValueError): Q.compile_query(invalid, question)
        self.assertEqual(Q.compile_query({"context":["children"],"focus":["microRNA-101-3p"]},
                         "Does microRNA-101-3p relate to disease in children?"),
                         "((children)) AND ((microRNA AND 101 AND 3p))")

    def test_question_only_requests_and_changed_drafts_rejected(self):
        rows=[]
        for i in range(6):
            bound={"request_sha256":"fixture","raw_text":"What is the role of CD2 in diabetic nephropathy?"}
            rows.append({"item_code":str(i),"dry":False,"status":"pending_scientific_review",
                         "draft":bound["raw_text"],**bound,"content_sha256":Q.digest(bound)})
        cfg={"id":"fixture","provider":"fixture"}
        reqs=Q.request_plan(rows,cfg,"instructions")
        for r in reqs:
            self.assertEqual(set(json.loads(r["body"]["messages"][1]["content"])),{"question"})
            self.assertEqual(len(r["body"]["messages"]),2)
        rows[0]["draft"]="A different question?"
        with self.assertRaisesRegex(ValueError,"changed"): Q.request_plan(rows,cfg,"instructions")

    def test_completed_invalid_output_is_not_rerolled_and_http_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); package=root/'protocol';package.mkdir()
            (package/'PROMPT.txt').write_text('Extract context and focus.')
            (package/'PROTOCOL.md').write_text('Fixture method.')
            rows=[]
            for i in range(6):
                b={"request_sha256":"fixture","raw_text":"What is the role of CD2 in diabetic nephropathy?"}
                rows.append({"item_code":str(i),"dry":False,"status":"pending_scientific_review",
                             "draft":b['raw_text'],**b,"content_sha256":Q.digest(b)})
            drafts=root/'drafts.jsonl';drafts.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            calls=[]
            def chat(model,provider,messages,**kw):
                idx=len(calls);calls.append(messages)
                content='{"needs_review":true}' if idx==0 else '{"context":["diabetic nephropathy"],"focus":["CD2"]}'
                response={"choices":[{"message":{"content":content},"finish_reason":"stop"}],"usage":{"cost":.01}}
                body={"model":model,"provider":Q.openrouter._provider(provider),"messages":messages,
                      **{k:kw[k] for k in ('temperature','top_p','max_tokens')}}
                kw['log']({"kind":"request","uid":str(idx),"utc":"fixture","body":body})
                kw['log']({"kind":"response","uid":str(idx),"utc":"fixture","http_status":200,"body":response})
                return response,0
            log=root/'run'
            with mock.patch.object(Q,'PACKAGE',package), mock.patch.object(Q.openrouter,'chat',side_effect=chat):
                Q.run(drafts,log,None,True)
                self.assertEqual(len(calls),0)
                with self.assertRaisesRegex(SystemExit,'unresolved'): Q.run(drafts,log,1)
                self.assertEqual(len(calls),6)
                self.assertFalse((log/'query-plan.json').exists())
                with self.assertRaisesRegex(SystemExit,'unresolved'): Q.run(drafts,log,1)
                self.assertEqual(len(calls),6)
                records=(log/'queries.jsonl').read_text().splitlines()
                (log/'queries.jsonl').write_text('\n'.join(records[:-1])+'\n')
                with self.assertRaisesRegex(SystemExit,'unresolved'): Q.run(drafts,log,1)
                self.assertEqual(len(calls),6)
                self.assertTrue(json.loads((log/'queries.jsonl').read_text().splitlines()[-1])['recovered_from_http'])
                self.assertAlmostEqual(json.loads((log/'summary.json').read_text())['known_cost_usd'],.06)


if __name__=='__main__':unittest.main()
