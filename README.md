
#For the judges use the deployed link to access the working exe file.

# ShareSafe Radar

> **Real-Time Automated Clipboard Redaction for Windows**  
> Protect sensitive data, API keys, and PII from accidental leaks in screenshots before you paste them into Slack, Discord, LLMs, or public documents.

---

## Overview

**ShareSafe Radar** is a lightweight, background Windows desktop application that continuously monitors your clipboard for image captures (e.g., via `Win + Shift + S`). 

When an image screenshot is detected:
1. It is processed in real time via an **AWS Lambda + Amazon Textract** OCR pipeline.
2. If sensitive information (API keys, passwords, credentials, or PII) is detected, the engine overlays dark redaction boxes over the leak.
3. The sanitized image is automatically placed back into your clipboard ready for safe sharing.
4. An unredacted original copy is temporarily saved in a local 24-hour expiring cache as a failsafe recovery option.

---

## Architecture & Workflow

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 WINDOWS CLIENT                                  │
│                                                                                 │
│  [ PrintScreen / Win+Shift+S ] ──> Clipboard ──> Background Monitor Thread     │
│                                                          │                      │
│  Local AppData History <── [ Failsafe Storage ] ─────────┼                      │
│  (Auto-expires in 24h)                                   │                      │
│                                                          ▼                      │
│                                                  [ Base64 Image Payload ]       │
└──────────────────────────────────────────────────────────┬──────────────────────┘
                                                           │ (HTTPS + x-api-key)
                                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                AWS CLOUD BACKEND                                │
│                                                                                 │
│  API Gateway (Rate Limited) ──> AWS Lambda Engine ──> Amazon Textract (OCR/PII)│
│                                                              │                  │
│  Redacted Image Output <────── [ Apply Bounding Boxes ] <────┘                  │
└─────────────────────────────────────────────────────────────────────────────────┘

```

---

## Key Features

* Real-Time Clipboard Monitoring:** Operates in a dedicated background thread with minimal CPU overhead.
* Intelligent PII & Secret Detection:** Leverages Amazon Textract to parse bounding boxes of sensitive text strings.
* Failsafe Local History:** Accidentally over-redacted a critical image? Access original unredacted captures directly from the dashboard.
* Zero-Retention Cache Policy:** Local original captures are automatically purged after 24 hours from `%LOCALAPPDATA%\ShareSafe_History`.
* Windows System Tray Integration:** Closes seamlessly into the system tray (`pystray`) to run silently without cluttering your taskbar.
* Dynamic Configuration Security:** Keeps AWS credentials out of source code using runtime `config.json` resolution—safe for GitHub releases.
* Windows Toast Notifications:** Instant desktop alerts notify you whenever a clipboard payload is actively redacted.

---

## Tech Stack

### Desktop Application (Client)

* **Python 3.10+**
* **Tkinter**: Dark-themed user dashboard with live thumbnail previews.
* **Pillow (PIL)**: Image manipulation and thumbnail rendering.
* **PyWin32 (`win32clipboard`)**: Low-level Windows clipboard API integration.
* **PyStray**: Windows System Tray minimization and context menu.
* **Plyer**: Native Windows Toast notifications.
* **PyInstaller**: Standalone single-file `.exe` compilation.

### Cloud Engine (Backend)

* **AWS API Gateway**: REST API endpoint with API Key requirement and rate throttling.
* **AWS Lambda**: Serverless Python execution engine.
* **Amazon Textract**: High-accuracy OCR engine for text coordinate extraction.

---

## Repository Structure

```text
ShareSafe-Radar/
│
├── client/
│   ├── app.py                   # Main GUI & background clipboard scanner engine
│   ├── config.json.example      # Template configuration file for deployment
│   └── requirements.txt         # Python dependencies for the desktop app
│
├── backend/
│   └── lambda_function.py       # AWS Lambda Textract redaction engine
│
├── .gitignore                   # Excludes secrets, build outputs, and local history
└── README.md

```

---

## ☁️ AWS Cloud Backend Setup

To run your own instance of the ShareSafe Radar backend, you will need to deploy the provided `lambda_function.py` to AWS.

### 1. Configure IAM Permissions

Your Lambda function needs permission to call Amazon Textract.

1. In the AWS IAM Console, create a new Role for an AWS Service (Lambda).
2. Attach the `AmazonTextractFullAccess` policy (or create a custom inline policy restricting access to `textract:DetectDocumentText`).
3. Attach the basic Lambda execution role (for CloudWatch logging).

### 2. Create the Lambda Function

1. Navigate to the **AWS Lambda Console** and click **Create function**.
2. Name it `RadarRedactionEngine` and select **Python 3.10** (or higher) as the runtime.
3. Under **Execution role**, select the IAM role you created in Step 1.
4. Copy the contents of `backend/lambda_function.py` from this repository and paste it into the Lambda code editor. Click **Deploy**.
5. *Note: If your Lambda function uses external libraries like Pillow for image manipulation, you will need to upload them as a Lambda Layer or package them in a `.zip` file.*

### 3. Set Up API Gateway

1. Navigate to **API Gateway** and create a new **REST API**.
2. Create a `POST` method and link it to your `RadarRedactionEngine` Lambda function.
3. **Secure the Endpoint**:
* Under Method Request, set **API Key Required** to `true`.
* Create a new **API Key** and a **Usage Plan**.
* Link the Usage Plan to your API Stage and enforce rate limits (e.g., 2 requests/second) to prevent credit drain.


4. Click **Deploy API** and copy the **Invoke URL**.

---

## Desktop Client Setup

### Prerequisites

* **Windows 10 / 11**
* **Python 3.8+** installed and added to `PATH`

### Local Installation

1. **Clone the Repository:**
```bash
git clone [https://github.com/YOUR_USERNAME/ShareSafe-Radar.git](https://github.com/YOUR_USERNAME/ShareSafe-Radar.git)
cd ShareSafe-Radar/client

```


2. **Create a Virtual Environment:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1

```


3. **Install Dependencies:**
```powershell
pip install -r requirements.txt

```


4. **Set Up Local Credentials:**
Copy `config.json.example` to `config.json` in the `client` folder:
```powershell
copy config.json.example config.json

```


Open `config.json` and insert your AWS API Gateway endpoint URL and API Key:
```json
{
  "AWS_API_ENDPOINT": "[https://your-api-id.execute-api.region.amazonaws.com/default/RadarRedactionEngine](https://your-api-id.execute-api.region.amazonaws.com/default/RadarRedactionEngine)",
  "X_API_KEY": "your_actual_aws_api_key_here"
}

```


5. **Run the Application:**
```powershell
python app.py

```



---

## Building the Executable (`.exe`)

To compile the application into a single standalone Windows executable that doesn't require Python to be installed:

```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name "ShareSafe_Radar" --hidden-import "plyer.platforms.win.notification" --hidden-import "win32clipboard" app.py

```

### Important Runtime Setup for the `.exe`:

The application utilizes a PyInstaller-safe path loader.

1. Navigate to the generated `dist/` directory.
2. Ensure your active `config.json` file is located **in the exact same directory** as the compiled `ShareSafe_Radar.exe`.

---

## Security & Cost Safeguards

To protect against API abuse, unauthorized access, and unexpected cloud costs:

1. **API Key Authentication (`x-api-key`):** The API Gateway endpoint rejects any outside request that lacks the valid header key.
2. **Throttling & Rate Limits:** Configured in AWS API Gateway Usage Plans to block spamming.
3. **AWS Budget Alerts:** Set up $0–$5 threshold alerts in the AWS Billing Console to notify via email if usage spikes.
4. **Git Exclusions:** The `.gitignore` prevents `config.json` (containing your live API Key) and local cached images from ever being committed to GitHub.

```

```
