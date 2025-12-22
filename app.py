from flask import Flask, render_template, request, send_file, jsonify
from boxMaker_v3 import make_3d_outline_gcode
import os
import tempfile
import atexit

app = Flask(__name__)

# Track temporary files for cleanup
temp_files = []

def cleanup_temp_files():
    """Clean up temporary files on exit"""
    for file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass

atexit.register(cleanup_temp_files)

@app.route('/')
def index():
    """Render the main form page"""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_gcode():
    """Handle form submission and generate gcode file"""
    temp_file_path = None
    try:
        # Get form data
        width = float(request.form.get('width', 0))
        length = float(request.form.get('length', 0))
        height = float(request.form.get('height', 0))
        unit = request.form.get('unit', 'mm').lower()
        filename = request.form.get('filename', 'box').strip()
        
        # Validate inputs
        if width <= 0 or length <= 0 or height <= 0:
            return jsonify({'error': 'All dimensions must be greater than 0'}), 400
        
        if not filename:
            return jsonify({'error': 'Filename cannot be empty'}), 400
        
        # Convert to millimeters if needed
        if unit in ['in', 'inch', 'inches']:
            width *= 25.4
            length *= 25.4
            height *= 25.4
        elif unit not in ['mm', 'millimeter', 'millimeters']:
            return jsonify({'error': f'Invalid unit: {unit}. Use mm or in'}), 400
        
        # Generate gcode file
        # Use a temporary directory to store the file
        temp_dir = tempfile.gettempdir()
        # Pass filename without extension - function will add .TAP
        temp_filename_base = os.path.join(temp_dir, filename)
        
        # Generate the gcode (function adds .TAP extension)
        gcode_file = make_3d_outline_gcode(width, length, height, temp_filename_base)
        temp_file_path = gcode_file
        
        # Track for cleanup
        temp_files.append(gcode_file)
        
        # Send file for download
        response = send_file(
            gcode_file,
            as_attachment=True,
            download_name=filename + '.TAP',
            mimetype='text/plain'
        )
        # Explicitly set Content-Disposition header to ensure filename is correct
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}.TAP"'
        return response
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
    finally:
        # Note: We don't delete immediately as Flask needs to send the file
        # Cleanup happens on exit via atexit
        pass

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

