"""
Servidor Flask - Compresor PDF de máxima calidad y velocidad
Estrategia dual: pikepdf (estructura) + Ghostscript (imágenes)
Deploy: Render.com con Dockerfile
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess, tempfile, os, time, shutil

app = Flask(__name__)
CORS(app, expose_headers=["X-Original-Size","X-Compressed-Size","X-Reduction","X-Time"])

PERFILES = {
    "extreme": {
        "label": "Máxima",
        "setting": "/screen",
        "dpi_color": 96,
        "dpi_gray": 96,
    },
    "recommended": {
        "label": "Óptima",
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

def comprimir_con_pikepdf(input_path, output_path):
    """
    Paso 1: pikepdf — limpieza estructural profunda sin tocar calidad visual.
    Elimina objetos huérfanos, streams duplicados, metadatos, thumbnails,
    y recomprime la tabla de objetos con QPDF.
    """
    try:
        import pikepdf
        with pikepdf.open(input_path, suppress_warnings=True) as pdf:
            # Eliminar metadatos innecesarios
            with pdf.open_metadata() as meta:
                for key in list(meta.keys()):
                    try: del meta[key]
                    except: pass

            # Eliminar thumbnails embebidos en cada página
            for page in pdf.pages:
                if "/Thumb" in page:
                    del page["/Thumb"]

            pdf.save(
                output_path,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                recompress_flate=True,
                linearize=True,   # optimiza para web (carga página a página)
            )
        return True
    except Exception as e:
        print(f"pikepdf falló: {e}")
        return False

def comprimir_con_ghostscript(input_path, output_path, perfil="recommended"):
    """
    Paso 2: Ghostscript — recompresión de imágenes con calidad controlada.
    Usa /Average (rápido y casi igual que Bicubic), hilos múltiples.
    """
    p = PERFILES.get(perfil, PERFILES["recommended"])
    cmd = [
        "gs",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        f"-dPDFSETTINGS={p['setting']}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",
        "-dDetectDuplicateImages=true",
        "-dNumRenderingThreads=4",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        f"-dColorImageResolution={p['dpi_color']}",
        f"-dGrayImageResolution={p['dpi_gray']}",
        "-dMonoImageResolution=300",
        "-dColorImageDownsampleType=/Average",
        "-dGrayImageDownsampleType=/Average",
        "-dMonoImageDownsampleType=/Subsample",
        "-dColorImageFilter=/DCTEncode",
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dProcessColorModel=/DeviceRGB",
        "-dOptimize=true",
        f"-sOutputFile={output_path}",
        input_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return result.returncode == 0, result.stderr

def comprimir_pdf(input_path, output_path, perfil="recommended"):
    """
    Estrategia dual:
    1. pikepdf limpia la estructura → archivo intermedio
    2. Ghostscript recomprime imágenes → archivo final
    3. Se devuelve el menor de los tres (original, pikepdf, gs)
    """
    tmp_pike = input_path + "_pike.pdf"
    tmp_gs   = input_path + "_gs.pdf"

    try:
        tam_orig = os.path.getsize(input_path)
        mejor_path   = input_path
        mejor_tam    = tam_orig

        # Paso 1: pikepdf
        pike_ok = comprimir_con_pikepdf(input_path, tmp_pike)
        if pike_ok and os.path.exists(tmp_pike):
            tam_pike = os.path.getsize(tmp_pike)
            if tam_pike < mejor_tam:
                mejor_path = tmp_pike
                mejor_tam  = tam_pike

        # Paso 2: Ghostscript sobre el mejor resultado hasta ahora
        gs_ok, stderr = comprimir_con_ghostscript(mejor_path, tmp_gs, perfil)
        if gs_ok and os.path.exists(tmp_gs):
            tam_gs = os.path.getsize(tmp_gs)
            if tam_gs < mejor_tam:
                mejor_path = tmp_gs
                mejor_tam  = tam_gs

        # Copiar el mejor resultado al output final
        if mejor_path != output_path:
            shutil.copy2(mejor_path, output_path)

        return True, ""

    except Exception as e:
        return False, str(e)

    finally:
        for f in [tmp_pike, tmp_gs]:
            try:
                if os.path.exists(f): os.unlink(f)
            except: pass

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

    output_path = input_path + "_final.pdf"

    try:
        t0 = time.time()
        exito, stderr = comprimir_pdf(input_path, output_path, perfil)
        tiempo = round(time.time() - t0, 2)

        if not exito or not os.path.exists(output_path):
            return jsonify({"error": f"Error al comprimir: {stderr}"}), 500

        tam_original   = os.path.getsize(input_path)
        tam_comprimido = os.path.getsize(output_path)
        reduccion      = round((1 - tam_comprimido / tam_original) * 100, 1)
        nombre_salida  = archivo.filename.replace(".pdf", "_comprimido.pdf")

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
    port = int(os.environ.get("PORT", 5050))
    print(f"Servidor iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port)
