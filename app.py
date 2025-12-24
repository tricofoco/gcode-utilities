from flask import Flask, render_template, request, send_file, jsonify
from boxMaker_v3 import make_3d_outline_gcode
from surfacing_gcodev3 import generate_surfacing_gcode
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
        plunge_feed = float(request.form.get('plunge_feed', 200))
        cut_feed = float(request.form.get('cut_feed', 3000))
        feed_unit = request.form.get('feed_unit', 'mm/min')
        filename = request.form.get('filename', 'box').strip()
        
        # Validate inputs
        if width <= 0 or length <= 0 or height <= 0:
            return jsonify({'error': 'All dimensions must be greater than 0'}), 400
        
        if plunge_feed <= 0 or cut_feed <= 0:
            return jsonify({'error': 'Feed rates must be greater than 0'}), 400
        
        if not filename:
            return jsonify({'error': 'Filename cannot be empty'}), 400
        
        # Convert to millimeters if needed
        if unit in ['in', 'inch', 'inches']:
            width *= 25.4
            length *= 25.4
            height *= 25.4
        elif unit not in ['mm', 'millimeter', 'millimeters']:
            return jsonify({'error': f'Invalid unit: {unit}. Use mm or in'}), 400
        
        # Convert feed rates to mm/min if needed
        if feed_unit == 'in/min':
            plunge_feed *= 25.4
            cut_feed *= 25.4
        elif feed_unit not in ['mm/min', 'in/min']:
            return jsonify({'error': f'Invalid feed unit: {feed_unit}. Use mm/min or in/min'}), 400
        
        # Generate gcode file
        # Use a temporary directory to store the file
        temp_dir = tempfile.gettempdir()
        # Pass filename without extension - function will add .TAP
        temp_filename_base = os.path.join(temp_dir, filename)
        
        # Generate the gcode (function adds .TAP extension)
        gcode_file = make_3d_outline_gcode(width, length, height, temp_filename_base, plunge_feed, cut_feed)
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

@app.route('/generate_surfacing', methods=['POST'])
def generate_surfacing():
    """Handle surfacing form submission and generate gcode file"""
    temp_file_path = None
    try:
        # Get form data
        width = float(request.form.get('width', 0))
        length = float(request.form.get('length', 0))
        depth = float(request.form.get('depth', 0))
        stepover = float(request.form.get('stepover', 0))
        max_stepdown = float(request.form.get('max_stepdown', 0))
        retract_height = float(request.form.get('retract_height', 5.0))
        unit = request.form.get('unit', 'mm').lower()
        spindle_speed = float(request.form.get('spindle_speed', 12000))
        plunge_rate = float(request.form.get('plunge_rate', 15.0))
        feed_rate = float(request.form.get('feed_rate', 80.0))
        rate_unit = request.form.get('rate_unit', 'mm/min')
        filename = request.form.get('filename', 'surfacing').strip()
        
        # Validate inputs
        if width <= 0 or length <= 0 or depth <= 0:
            return jsonify({'error': 'Width, length, and depth must be greater than 0'}), 400
        
        if stepover <= 0 or max_stepdown <= 0:
            return jsonify({'error': 'Stepover and max stepdown must be greater than 0'}), 400
        
        if retract_height <= 0:
            return jsonify({'error': 'Retract height must be greater than 0'}), 400
        
        if feed_rate <= 0 or plunge_rate <= 0:
            return jsonify({'error': 'Feed rate and plunge rate must be greater than 0'}), 400
        
        if not filename:
            return jsonify({'error': 'Filename cannot be empty'}), 400
        
        # Normalize unit values to match function expectations
        if unit in ['in', 'inch', 'inches']:
            geom_unit = 'inch'
        elif unit in ['mm', 'millimeter', 'millimeters']:
            geom_unit = 'mm'
        else:
            return jsonify({'error': f'Invalid unit: {unit}. Use mm or in'}), 400
        
        # Normalize rate unit values
        if rate_unit in ['in/min', 'inch/min']:
            rate_unit_normalized = 'in/min'
        elif rate_unit == 'mm/min':
            rate_unit_normalized = 'mm/min'
        else:
            return jsonify({'error': f'Invalid rate unit: {rate_unit}. Use mm/min or in/min'}), 400
        
        # Convert retract_height to mm based on selected unit
        if geom_unit == 'inch':
            retract_z_mm = retract_height * 25.4
        else:  # mm
            retract_z_mm = retract_height
        
        # Generate G-code string
        gcode_string = generate_surfacing_gcode(
            width=width,
            length=length,
            final_depth=depth,
            max_stepdown=max_stepdown,
            stepover=stepover,
            unit=geom_unit,
            feed_rate=feed_rate,
            plunge_rate=plunge_rate,
            rate_unit=rate_unit_normalized,
            spindle_speed_rpm=spindle_speed,
            retract_z_mm=retract_z_mm,
            program_name=filename
        )
        
        # Create temporary file
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename + '.nc')
        
        # Write G-code to file
        with open(temp_file_path, 'w') as f:
            f.write(gcode_string)
        
        # Track for cleanup
        temp_files.append(temp_file_path)
        
        # Send file for download
        response = send_file(
            temp_file_path,
            as_attachment=True,
            download_name=filename + '.nc',
            mimetype='text/plain'
        )
        # Explicitly set Content-Disposition header to ensure filename is correct
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}.nc"'
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

