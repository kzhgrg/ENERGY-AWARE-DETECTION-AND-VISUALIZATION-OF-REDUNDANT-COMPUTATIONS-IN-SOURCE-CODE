from flask import Flask, jsonify, render_template, request
from analyzer import analyze
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100_000

@app.get('/')
def index(): return render_template('index.html')

@app.post('/analyze')
def run():
    data=request.get_json(silent=True) or {}
    code=data.get('code','')
    if not isinstance(code,str): return jsonify({'error':'Code must be text.'}),400
    return jsonify(analyze(code))

@app.post('/measure-energy')
def measure_energy():
    # Never execute browser-submitted code. Only a fixed, audited bundled benchmark.
    from energy_dashboard import run_energy_pair
    try:
        return jsonify(run_energy_pair())
    except Exception as exc:
        return jsonify({'error':str(exc)}), 422

if __name__=='__main__': app.run(host='127.0.0.1',port=5000,debug=True)
