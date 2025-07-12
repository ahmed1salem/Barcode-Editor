import os
import io
import time
import zipfile
from flask import Flask, request, send_file, Markup
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
from werkzeug.utils import secure_filename

# ----------------- الإعدادات والتكوين -----------------
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # تحديد أقصى حجم للملفات المرفوعة (16 ميجابايت)

# ----------------- قوالب HTML و CSS المدمجة -----------------

# تم دمج كود الـ CSS هنا مباشرة لتجنب الحاجة لملف خارجي
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>مولد الباركود المدمج</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-color: #007bff; --secondary-color: #f8f9fa; --dark-color: #343a40;
            --light-color: #ffffff; --font-family: 'Cairo', sans-serif;
        }
        body {
            font-family: var(--font-family); background-color: var(--secondary-color); color: var(--dark-color);
            margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px;
        }
        .container {
            background-color: var(--light-color); padding: 40px; border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1); width: 100%; max-width: 700px; text-align: center;
        }
        header h1 { color: var(--dark-color); margin-bottom: 10px; }
        header p { color: #6c757d; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; text-align: right; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: bold; }
        .form-group-inline { display: flex; gap: 20px; justify-content: space-between; }
        .form-group-inline .form-group { flex: 1; }
        textarea, input[type="file"], input[type="number"] {
            width: 100%; padding: 12px; border: 1px solid #ced4da; border-radius: 8px;
            font-family: var(--font-family); box-sizing: border-box; transition: border-color 0.3s;
        }
        textarea:focus, input:focus { outline: none; border-color: var(--primary-color); }
        button {
            width: 100%; padding: 15px; background-color: var(--primary-color); color: var(--light-color);
            border: none; border-radius: 8px; font-size: 18px; font-weight: bold; cursor: pointer;
            transition: background-color 0.3s; display: flex; justify-content: center; align-items: center;
        }
        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #6c757d; cursor: not-allowed; }
        .spinner {
            border: 3px solid rgba(255, 255, 255, 0.3); border-radius: 50%; border-top: 3px solid #fff;
            width: 20px; height: 20px; animation: spin 1s linear infinite;
        }
        .error { color: #dc3545; background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 8px; margin-bottom: 20px;}
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>مولد الباركود المدمج</h1>
            <p>أدخل الأكواد، ارفع تصميمك، واحصل على الصفحات جاهزة للطباعة.</p>
        </header>

        {error_message}

        <form action="/generate" method="post" enctype="multipart/form-data" id="generator-form">
            <div class="form-group">
                <label for="codes">1. الصق الأكواد هنا (كل كود في سطر جديد)</label>
                <textarea id="codes" name="codes" rows="10" placeholder="12345&#x0a;67890&#x0a;54321&#x0a;..." required></textarea>
            </div>

            <div class="form-group">
                <label for="template">2. ارفع صورة التصميم (الخلفية)</label>
                <input type="file" id="template" name="template" accept="image/jpeg, image/png" required>
            </div>
            
            <div class="form-group">
                <label for="font_file">3. ارفع ملف الخط (اختياري، سيتم استخدام خط داخلي إذا تُرك فارغًا)</label>
                <input type="file" id="font_file" name="font_file" accept=".ttf, .otf">
            </div>

            <div class="form-group-inline">
                 <div class="form-group">
                    <label for="font_size">حجم الخط</label>
                    <input type="number" id="font_size" name="font_size" value="30" required>
                </div>
                 <div class="form-group">
                    <label for="barcode_height">ارتفاع الباركود</label>
                    <input type="number" id="barcode_height" name="barcode_height" value="60" required>
                </div>
            </div>

            <button type="submit" id="submit-btn">
                <span class="btn-text">🚀 ابدأ التوليد</span>
                <span class="spinner" style="display: none;"></span>
            </button>
        </form>
    </div>

    <script>
        document.getElementById('generator-form').addEventListener('submit', function() {
            document.getElementById('submit-btn').disabled = true;
            document.querySelector('#submit-btn .btn-text').style.display = 'none';
            document.querySelector('#submit-btn .spinner').style.display = 'inline-block';
        });
    </script>
</body>
</html>
"""

# ----------------- الدوال المساعدة -----------------
def create_barcode_card(code, font_path, font_size, barcode_height):
    """تنشئ صورة تحتوي على باركود ونص الكود أسفله."""
    try:
        code128 = barcode.get('code128', code, writer=ImageWriter())
        options = {'module_height': barcode_height, 'write_text': False, 'background': 'transparent'}
        barcode_pil = code128.render(options)

        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default(size=font_size)
        text_bbox = ImageDraw.Draw(Image.new('RGB', (1,1))).textbbox((0, 0), code, font=font)
        text_width, text_height = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        
        card_width = barcode_pil.width
        card_height = barcode_pil.height + text_height + 15

        final_card = Image.new('RGBA', (card_width, card_height), (0, 0, 0, 0))
        final_card.paste(barcode_pil, (0, 0))
        
        draw = ImageDraw.Draw(final_card)
        text_x = (card_width - text_width) / 2
        text_y = barcode_pil.height + 5
        draw.text((text_x, text_y), code, font=font, fill='black')
        
        return final_card
    except Exception as e:
        print(f"Error creating barcode for '{code}': {e}")
        return None

# ----------------- مسارات التطبيق (Routes) -----------------
@app.route('/')
def index():
    """عرض الصفحة الرئيسية."""
    return Markup(HTML_TEMPLATE.format(error_message=""))

@app.route('/generate', methods=['POST'])
def generate():
    """معالجة الطلب وتوليد الملفات."""
    # **ملاحظة هامة:** عدّل هذه الإحداثيات لتناسب تصميمك بدقة
    # الإحداثيات هي (المسافة من اليسار، المسافة من الأعلى)
    POSITIONS = [
        (110, 415), (850, 415), (110, 950), (850, 950),
        (110, 1485), (850, 1485), (110, 2020), (850, 2020),
    ]

    try:
        codes_text = request.form['codes']
        template_file = request.files.get('template')
        font_file = request.files.get('font_file')
        font_size = int(request.form['font_size'])
        barcode_height = float(request.form['barcode_height'])
        
        if not codes_text or not template_file:
            error = '<div class="error">خطأ: الرجاء لصق الأكواد ورفع صورة التصميم.</div>'
            return Markup(HTML_TEMPLATE.format(error_message=error))

        codes = [code.strip() for code in codes_text.splitlines() if code.strip()]
        
        template_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(template_file.filename))
        template_file.save(template_path)
        
        font_path = None
        if font_file:
            font_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(font_file.filename))
            font_file.save(font_path)

        page_files = []
        for i, page_num in enumerate(range(0, len(codes), 8)):
            batch = codes[page_num:page_num+8]
            page_template = Image.open(template_path).convert("RGBA")
            
            for j, code in enumerate(batch):
                if j < len(POSITIONS):
                    barcode_card = create_barcode_card(code, font_path, font_size, barcode_height)
                    if barcode_card:
                        page_template.paste(barcode_card, POSITIONS[j], barcode_card)
            
            output_filename = f'page_{i+1}.png'
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            page_template.convert("RGB").save(output_path, 'PNG', quality=95)
            page_files.append(output_path)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in page_files:
                zf.write(file_path, os.path.basename(file_path))
        
        # تنظيف الملفات المؤقتة
        for file_path in [template_path, font_path, *page_files]:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        
        zip_buffer.seek(0)
        return send_file(zip_buffer, as_attachment=True, download_name=f'barcodes_{time.strftime("%Y%m%d")}.zip', mimetype='application/zip')

    except Exception as e:
        print(f"An error occurred: {e}")
        error = f'<div class="error">حدث خطأ غير متوقع: {e}</div>'
        return Markup(HTML_TEMPLATE.format(error_message=error))

if __name__ == '__main__':
    # لتشغيل التطبيق محلياً
    app.run(debug=True)
