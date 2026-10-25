import json, os, subprocess, sys, tempfile, time, unittest, urllib.request, urllib.error, socket
class HTTPTests(unittest.TestCase):
    def test_health_and_token_gate(self):
        with tempfile.TemporaryDirectory() as d:
            env=os.environ.copy()
            env.update({"PORT":"18765","SOLVEEASE_DB_PATH":d+"/db.sqlite3","SOLVEEASE_RUN_TOKEN":"test-secret"})
            p=subprocess.Popen([sys.executable,"app.py"],cwd=os.path.dirname(os.path.dirname(__file__)),env=env,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                ready=False
                for _ in range(50):
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:18765/health",timeout=.5) as r:
                            self.assertEqual(json.loads(r.read()),{"ok":True,"service":"solveease","version":"2.0"})
                            ready=True; break
                    except Exception: time.sleep(.1)
                self.assertTrue(ready,"server did not start")
                req=urllib.request.Request("http://127.0.0.1:18765/api/run",method="POST")
                with self.assertRaises(urllib.error.HTTPError) as ctx: urllib.request.urlopen(req,timeout=2)
                self.assertEqual(ctx.exception.code,401)
            finally:
                p.terminate()
                try: p.wait(timeout=3)
                except subprocess.TimeoutExpired: p.kill()
if __name__=="__main__": unittest.main()
