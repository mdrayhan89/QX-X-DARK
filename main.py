import os
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import traceback

# ------------------ Quotex Import with Fallback ------------------
try:
    from quotexpy import Quotex
    print("✓ Imported Quotex from quotexpy")
except ImportError:
    try:
        from quotexpy.main import Quotex
        print("✓ Imported Quotex from quotexpy.main")
    except ImportError as e:
        print(f"✗ Failed to import Quotex: {e}")
        Quotex = None

# ------------------ Configuration ------------------
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Credentials (hardcoded as requested)
EMAIL = "trrayhanislam786@gmail.com"
PASSWORD = "Mdrayhan@655"

# Global variables for Quotex client and connection status
quotex_client = None
client_lock = threading.Lock()
is_connected = False
last_connection_attempt = 0
RECONNECT_INTERVAL = 300  # 5 minutes

# ------------------ Playwright Stealth Login ------------------
def login_to_quotex():
    """Login to Quotex using Playwright with stealth and extract SSID"""
    global quotex_client, is_connected
    
    try:
        from playwright.sync_api import sync_playwright
        import playwright_stealth
        
        print(f"[{datetime.now()}] Starting Playwright stealth login...")
        
        with sync_playwright() as p:
            # Launch browser with stealth settings
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = context.new_page()
            
            # Apply stealth
            playwright_stealth.stealth_sync(page)
            
            # Navigate to Quotex
            page.goto('https://quotex.io/en', timeout=60000)
            time.sleep(2)
            
            # Click login button
            page.click('button:has-text("Login")')
            time.sleep(1)
            
            # Fill credentials
            page.fill('input[name="email"]', EMAIL)
            page.fill('input[name="password"]', PASSWORD)
            time.sleep(0.5)
            
            # Submit
            page.click('button[type="submit"]')
            time.sleep(5)  # Wait for login to complete
            
            # Get cookies
            cookies = context.cookies()
            browser.close()
            
            # Extract SSID token
            ssid = None
            for cookie in cookies:
                if cookie.get('name') == 'ssid':
                    ssid = cookie.get('value')
                    break
            
            if ssid:
                print(f"[{datetime.now()}] ✓ SSID extracted successfully")
                
                # Initialize Quotex client with SSID
                with client_lock:
                    global quotex_client
                    if Quotex is not None:
                        quotex_client = Quotex()
                        quotex_client.set_ssid(ssid)
                        is_connected = True
                        print(f"[{datetime.now()}] ✓ Quotex client initialized with SSID")
                    else:
                        print(f"[{datetime.now()}] ✗ Quotex library not available")
                        is_connected = False
                return True
            else:
                print(f"[{datetime.now()}] ✗ SSID not found in cookies")
                is_connected = False
                return False
                
    except Exception as e:
        print(f"[{datetime.now()}] Login error: {e}")
        traceback.print_exc()
        is_connected = False
        return False

def background_login_worker():
    """Background thread to maintain Quotex connection"""
    global last_connection_attempt
    
    while True:
        try:
            current_time = time.time()
            if not is_connected or (current_time - last_connection_attempt) > RECONNECT_INTERVAL:
                print(f"[{datetime.now()}] Attempting to connect to Quotex...")
                last_connection_attempt = current_time
                login_to_quotex()
            
            # Keep connection alive with a ping every 30 seconds
            if is_connected and quotex_client:
                try:
                    # Simple ping to check connection
                    quotex_client.get_profile()
                except:
                    print(f"[{datetime.now()}] Connection lost, will reconnect")
                    is_connected = False
            
            time.sleep(30)  # Check every 30 seconds
            
        except Exception as e:
            print(f"[{datetime.now()}] Background worker error: {e}")
            time.sleep(60)

# ------------------ Helper Functions ------------------
def determine_candle_color(open_val, close_val):
    """Determine candle color based on open and close"""
    try:
        o = float(open_val)
        c = float(close_val)
        if c > o:
            return "green"
        elif c < o:
            return "red"
        else:
            return "doji"
    except:
        return "doji"

def fetch_candles(pair, count):
    """Fetch candles using quotexpy client"""
    global quotex_client, is_connected
    
    if not is_connected or quotex_client is None:
        raise Exception("Quotex client not connected. Please try again in a moment.")
    
    try:
        # Using M1 timeframe as specified
        timeframe = "M1"
        candles = quotex_client.get_candles(pair, timeframe, count)
        
        if not candles:
            return []
        
        formatted_data = []
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for idx, candle in enumerate(candles):
            # Handle different possible candle formats from quotexpy
            if isinstance(candle, dict):
                candle_time = candle.get('time', candle.get('timestamp', ''))
                open_price = candle.get('open', 0)
                high_price = candle.get('high', 0)
                low_price = candle.get('low', 0)
                close_price = candle.get('close', 0)
                volume = candle.get('volume', 48)
            else:
                # If candle is a tuple or list
                candle_time = candle[0] if len(candle) > 0 else ''
                open_price = candle[1] if len(candle) > 1 else 0
                high_price = candle[2] if len(candle) > 2 else 0
                low_price = candle[3] if len(candle) > 3 else 0
                close_price = candle[4] if len(candle) > 4 else 0
                volume = candle[5] if len(candle) > 5 else 48
            
            # Convert timestamp to readable format if needed
            if isinstance(candle_time, (int, float)):
                candle_time = datetime.fromtimestamp(candle_time).strftime("%Y-%m-%d %H:%M:%S")
            elif not candle_time:
                candle_time = current_time
            
            color = determine_candle_color(open_price, close_price)
            
            formatted_data.append({
                "id": str(idx + 1),
                "pair": pair,
                "timeframe": timeframe,
                "candle_time": str(candle_time),
                "open": str(open_price),
                "high": str(high_price),
                "low": str(low_price),
                "close": str(close_price),
                "volume": str(volume),
                "color": color,
                "created_at": current_time
            })
        
        return formatted_data
        
    except Exception as e:
        print(f"Error fetching candles: {e}")
        traceback.print_exc()
        raise Exception(f"Failed to fetch candles: {str(e)}")

# ------------------ Flask Routes ------------------
@app.route('/', methods=['GET'])
def get_candles():
    """Main endpoint to fetch historical candle data"""
    try:
        # Get query parameters
        pair = request.args.get('pair', 'EURUSD_otc')
        count = request.args.get('count', 1)
        
        # Validate count
        try:
            count = int(count)
            if count < 1:
                count = 1
            elif count > 3000:
                count = 3000
        except ValueError:
            count = 1
        
        # Check connection
        if not is_connected or quotex_client is None:
            return jsonify({
                "Owner_Developer": "DARK-X-RAYHAN",
                "Telegram": "@mdrayhan85",
                "Channel": "https://t.me/mdrayhan85",
                "success": False,
                "count": 0,
                "data": [],
                "error": "Quotex client is not connected. Please wait for connection to establish."
            }), 503
        
        # Fetch candles
        candle_data = fetch_candles(pair, count)
        
        # Return success response
        return jsonify({
            "Owner_Developer": "DARK-X-RAYHAN",
            "Telegram": "@mdrayhan85",
            "Channel": "https://t.me/mdrayhan85",
            "success": True,
            "count": len(candle_data),
            "data": candle_data
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"API Error: {error_msg}")
        traceback.print_exc()
        
        return jsonify({
            "Owner_Developer": "DARK-X-RAYHAN",
            "Telegram": "@mdrayhan85",
            "Channel": "https://t.me/mdrayhan85",
            "success": False,
            "count": 0,
            "data": [],
            "error": error_msg
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "healthy",
        "connected": is_connected,
        "timestamp": datetime.now().isoformat()
    })

# ------------------ Main Entry Point ------------------
if __name__ == '__main__':
    # Start background login thread
    login_thread = threading.Thread(target=background_login_worker, daemon=True)
    login_thread.start()
    
    # Give initial login a moment to start
    time.sleep(2)
    
    # Get port from environment variable (for Render)
    port = int(os.environ.get('PORT', 5000))
    
    # Run Flask app
    print(f"[{datetime.now()}] Starting Flask server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
