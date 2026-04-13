"""
Endpoint /dev/exec — permette a Claude di eseguire script Python in autonomia.
Avviare con: python3 dev_exec.py (porta 5099)
"""
from flask import Flask, request, jsonify
import subprocess, os, tempfile, sys

app = Flask(__name__)
REPO = '/Users/iondodon/Documents/tool-db-manager'

@app.route('/exec', methods=['POST'])
def exec_script():
    data = request.json
    script = data.get('script', '')
    if not script:
        return jsonify({'error': 'no script'})
    
    # Scrivi script in file temp ed esegui
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(f"import os\nos.chdir('{REPO}')\n")
        f.write(script)
        tmp = f.name
    
    try:
        r = subprocess.run([sys.executable, tmp], capture_output=True, text=True, timeout=30, cwd=REPO)
        return jsonify({'stdout': r.stdout, 'stderr': r.stderr, 'rc': r.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'timeout'})
    finally:
        os.unlink(tmp)

@app.route('/read', methods=['GET'])
def read_file():
    path = request.args.get('path','')
    full = os.path.join(REPO, path)
    if not os.path.exists(full):
        return jsonify({'error': 'not found'})
    return jsonify({'content': open(full, encoding='utf-8').read()})

@app.route('/write', methods=['POST'])
def write_file():
    data = request.json
    path = data.get('path','')
    content = data.get('content','')
    full = os.path.join(REPO, path)
    open(full, 'w', encoding='utf-8').write(content)
    # Auto git add+commit+push
    msg = data.get('msg', 'auto update')
    subprocess.run(['git','add', path], cwd=REPO)
    subprocess.run(['git','commit','-m', msg], cwd=REPO, capture_output=True)
    r = subprocess.run(['git','push','origin','main1'], cwd=REPO, capture_output=True, text=True)
    return jsonify({'ok': True, 'push': r.stdout or r.stderr})

if __name__ == '__main__':
    print("Dev exec server su http://localhost:5099")
    app.run(port=5099, debug=False)
