import json
import base64
import io
import re
import boto3
from PIL import Image, ImageDraw

# Initialize AWS clients
textract = boto3.client('textract')
comprehend = boto3.client('comprehend')

# Regex rules for high-precision developer secrets
SENSITIVE_PATTERNS = [
    r'AKIA[0-9A-Z]{16}',                              # AWS Access Key
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'  # Email Address
]

def lambda_handler(event, context):
    try:
        # 1. Receive Base64 payload from API Gateway
        body = json.loads(event.get('body', '{}'))
        image_b64 = body.get('image_base64')
        if not image_b64:
            return {"statusCode": 400, "body": "No image provided."}

        # Strip header if present (e.g., 'data:image/png;base64,...')
        if ',' in image_b64:
            image_b64 = image_b64.split(',')[1]

        # 2. Decode into RAM (Zero-Retention Policy)
        image_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(image_bytes))
        img_width, img_height = image.size
        
        # 3. Call Amazon Textract
        response = textract.detect_document_text(Document={'Bytes': image_bytes})
        
        draw = ImageDraw.Draw(image)
        redacted_items = []
        
        # 4. Process Bounding Boxes & Redact
        for item in response.get('Blocks', []):
            if item['BlockType'] == 'LINE':
                text = item['Text']
                
                # Check against Regex
                is_sensitive = any(re.search(p, text) for p in SENSITIVE_PATTERNS)
                
                # Optional: Send text to Comprehend for PII detection
                if not is_sensitive and len(text) > 4:
                    comp_res = comprehend.detect_pii_entities(Text=text, LanguageCode='en')
                    if comp_res.get('Entities'):
                        is_sensitive = True

                if is_sensitive:
                    # Textract returns coordinates as percentages (0.0 to 1.0)
                    box = item['Geometry']['BoundingBox']
                    x0 = box['Left'] * img_width
                    y0 = box['Top'] * img_height
                    x1 = x0 + (box['Width'] * img_width)
                    y1 = y0 + (box['Height'] * img_height)
                    
                    # Draw solid black rectangle
                    draw.rectangle([x0, y0, x1, y1], fill="black")
                    redacted_items.append(text)

        # 5. Re-encode the sanitized image to Base64
        output_buffer = io.BytesIO()
        image.save(output_buffer, format="PNG")
        sanitized_b64 = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
        
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "leak_detected": len(redacted_items) > 0,
                "redacted_image": sanitized_b64,
                "summary": [f"Item Redacted ({len(redacted_items)} total)"]
            })
        }

    except Exception as e:
        return {"statusCode": 500, "body": str(e)}