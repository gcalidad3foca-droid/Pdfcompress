"""
Servidor Flask + Ghostscript - Compresor PDF
Deploy en Render.com (plan gratuito)
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import tempfile
import os
import time

app = Flask(__name__)

# CORS abierto — ajusta el origen si quieres restringirlo a tu GitHub Pages
CORS(app, expose_headers=["X-Original-Size", "X-Compressed-Size", "X-Reduction", "X-Time"])

PERFILES = {
    "extreme": {
        "label": "Extrema",
        "setting": "/screen",
        "dpi_color": 72,
        "dpi_gray": 72,
    },
    "recommended": {
        "label": "Recomendada",
        "setting": "/ebook",
        "dpi_color": 150,
        "dpi_gray": 150,
    },
    "less": {
        "label": "Alta calidad",
        "setting": "/printer",
        "dpi_color": 300,
        "dpi_gray": 300,
    }
}

def comprimir_pdf(input_path, output_path, perfil="recommended"):
    p = PERFILES.get(perfil, PERFILES["recommended"])
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        f"-dPDFSETTINGS={p['setting']}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH",
        "-dCompressFonts=true", "-dSubsetFonts=true", "-dEmbedAllFonts=true",
        f"-dColorImageResolution={p['dpi_color']}",
        f"-dGrayImageResolution={p['dpi_gray']}",
        "-dMonoImageResolution=300",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dOptimize=true",
        f"-sOutputFile={output_path}",
        input_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0, result.stderr

@app.route("/comprimir", methods=["POST"])
def comprimir():
    if "pdf" not in request.files:
        return jsonify({"error": "No se recibió archivo PDF"}), 400

    archivo = request.files["pdf"]
    perfil  = request.form.get("perfil", "recommended")

    if not archivo.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser PDF"}), 400

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in:
        archivo.save(tmp_in.name)
        input_path = tmp_in.name

    output_path = input_path.replace(".pdf", "_out.pdf")

    try:
        t0 = time.time()
        exito, stderr = comprimir_pdf(input_path, output_path, perfil)
        tiempo = round(time.time() - t0, 2)

        if not exito or not os.path.exists(output_path):
            return jsonify({"error": f"Ghostscript falló: {stderr}"}), 500

        tam_original  = os.path.getsize(input_path)
        tam_comprimido = os.path.getsize(output_path)
        reduccion     = round((1 - tam_comprimido / tam_original) * 100, 1)
        nombre_salida = archivo.filename.replace(".pdf", "_comprimido.pdf")

        response = send_file(
            output_path,
            as_attachment=True,
            download_name=nombre_salida,
            mimetype="application/pdf"
        )
        response.headers["X-Original-Size"]   = str(tam_original)
        response.headers["X-Compressed-Size"] = str(tam_comprimido)
        response.headers["X-Reduction"]       = str(reduccion)
        response.headers["X-Time"]            = str(tiempo)
        return response

    finally:
        for f in [input_path, output_path]:
            try:
                if os.path.exists(f): os.unlink(f)
            except: pass

@app.route("/estado", methods=["GET"])
def estado():
    try:
        r = subprocess.run(["gs", "--version"], capture_output=True, text=True)
        return jsonify({"activo": True, "ghostscript": r.stdout.strip()})
    except:
        return jsonify({"activo": False}), 500

if __name__ == "__main__":
    # Render pasa el puerto por variable de entorno PORT
    port = int(os.environ.get("PORT", 5050))
    print(f"Servidor iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port)
