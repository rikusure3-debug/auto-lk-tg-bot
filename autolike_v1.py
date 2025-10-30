import asyncio
import json
import logging
import httpx
import pytz 
from datetime import datetime, date, timedelta, time 
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Configuration (Ager Information Ongsho) ---
# Token o Group ID ager-barer dewa-tai ache
BOT_TOKEN = "8024225954:AAF5lQ_L5GYCORO2Ulr4Nm7l9oM_uV8EdXk" 
ADMIN_USER_ID = 2098068100
ALLOWED_GROUP_ID = -4835590895
# --------------------------------------------------------

# --- Automatic Job Configuration (Notun System) ---
BD_TIMEZONE = pytz.timezone("Asia/Dhaka") # Bangladesh Time (GMT+6)

# Fallback time (jodi config.json na thake ba /settime use na kora hoy)
DEFAULT_SCHEDULED_HOUR_BD = 4
DEFAULT_SCHEDULED_MINUTE_BD = 0
# ----------------------------------------

JSON_FILE = "uids.json"
CONFIG_FILE = "config.json" # <-- NOTUN FILE: Schedule time save korar jonno
API_BASE_URL = "https://raigen-s-like-bot-eta.vercel.app/like"
SERVER_NAME = "bd"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

processing_lock = asyncio.Lock()

# --- JSON Data Helper Functions ---

def load_uids():
    """uids.json file aage theke thakle setake load korbe, na thakle empty list return korbe."""
    try:
        with open(JSON_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_uids(uids_data):
    """UID list-ke uids.json file-e save korbe."""
    uids_data.sort(key=lambda x: x["serial"])
    with open(JSON_FILE, "w") as f:
        json.dump(uids_data, f, indent=4)

# --- Config (Schedule Time) Helper Functions (NOTUN) ---

def load_config():
    """config.json file theke settings load korbe."""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # File na thakle, fallback values use hobe
        return {}

def save_config(config_data):
    """Settings-gulo config.json file-e save korbe."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=4)

# --- API Helper Function (Browser Fix Shoho) ---

async def fetch_player_data(uid):
    """Diye dewa UID-er jonno like API-te call korbe, browser header shoho."""
    params = {"uid": uid, "server_name": SERVER_NAME}
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://raigen-s-like-bot-eta.vercel.app/" 
    }
    
    response_text = "" 
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            logger.info(f"Fetching data for UID {uid} from {API_BASE_URL}")
            response = await client.get(API_BASE_URL, params=params, timeout=30.0)
            response_text = response.text 
            
            logger.info(f"Response status for UID {uid}: {response.status_code}")
            
            if "application/json" not in response.headers.get("content-type", "").lower():
                logger.warning(f"API did not return JSON for UID {uid}. Content-Type: {response.headers.get('content-type')}")
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                     logger.error(f"Failed to decode non-JSON response for UID {uid}.")
                     return {"status": -1, "error": "API Error: Not JSON", "UID": uid, "PlayerNickname": "Unknown"}
            else:
                 data = response.json() 
            
            if response.status_code == 200 and data.get("status") == 1:
                logger.info(f"Successfully fetched data for UID {uid}")
                return data
            else:
                logger.warning(f"API call failed for UID {uid}. Status: {response.status_code}, JSON Response: {data}")
                error_msg = data.get("error", "API Error")
                if 'PlayerNickname' in data: 
                     return {"status": -1, "error": error_msg, "UID": uid, "PlayerNickname": data.get("PlayerNickname", "Unknown")}
                return {"status": -1, "error": error_msg, "UID": uid, "PlayerNickname": "Unknown"}
                
    except httpx.ConnectError as e:
        logger.error(f"Connection Error for UID {uid}: {e}")
        return {"status": -1, "error": "Connection Error", "UID": uid, "PlayerNickname": "Unknown"}
    except httpx.RequestError as e:
        logger.error(f"HTTPX RequestError for UID {uid}: {e}")
        return {"status": -1, "error": str(e), "UID": uid, "PlayerNickname": "Unknown"}
    except json.JSONDecodeError as e:
        logger.error(f"JSON Decode Error for UID {uid}: {e}. Response text: {response_text[:200]}")
        return {"status": -1, "error": "Failed to decode API response", "UID": uid, "PlayerNickname": "Unknown"}
    except Exception as e:
        logger.error(f"General error fetching UID {uid}: {e}")
        return {"status": -1, "error": str(e), "UID": uid, "PlayerNickname": "Unknown"}

# --- Helper function to check admin and group ---

def is_admin_in_allowed_group(update: Update) -> bool:
    """Check kore je command-ti shothik group ebong admin user-er aach kina."""
    if update.effective_chat.id != ALLOWED_GROUP_ID:
        logger.warning(f"Bot summoned in wrong group: {update.effective_chat.id}")
        return False
        
    if update.effective_user.id != ADMIN_USER_ID:
        logger.warning(f"Non-admin user {update.effective_user.id} tried to use bot.")
        return False
        
    return True

# --- Bot Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command. (UPDATE KORA)"""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID and update.effective_user.id != ADMIN_USER_ID:
            await update.message.reply_text("This is a private bot for admin use only.")
        return
    
    # Load current schedule time from config file
    config = load_config()
    scheduled_hour = config.get("scheduled_hour", DEFAULT_SCHEDULED_HOUR_BD)
    scheduled_minute = config.get("scheduled_minute", DEFAULT_SCHEDULED_MINUTE_BD)
        
    await update.message.reply_text(
        "Welcome Admin!\n"
        f"Ami shudhu ei group-ei (ID: {ALLOWED_GROUP_ID}) kaj korbo.\n"
        f"Automatic Like Job schedule kora ache protidin {scheduled_hour}:{scheduled_minute:02d} (BD Time).\n"
        "Commands:\n"
        "/add <uid> <days> - Notun UID add korun (kotodiner jonno).\n"
        "/remove <serial> - Serial number diye UID remove korun.\n"
        "/extend <serial> <days> - Kono UID-er meyed (validity) baran.\n"
        "/list - Shob saved UID-er list dekhun.\n"
        "/m - Shob *valid* UID-te *ekhoni* manually like pathan.\n"
        "/settime <HH:MM> - Automatic job-er time set korun (e.g., /settime 7:30)" # <-- Notun
    )

async def add_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Notun UID add korbe ebong expiry date set korbe."""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    try:
        uid_to_add = int(context.args[0])
        days_to_add = int(context.args[1])
        if days_to_add <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Wrong format. Use: /add <UID> <days>\nExample: /add 12345 30")
        return

    uids_data = load_uids()

    if any(user["uid"] == uid_to_add for user in uids_data):
        await update.message.reply_text(f"Error: UID {uid_to_add} already exists. Use /extend to add more days.")
        return

    await update.message.reply_text(f"Fetching data for UID {uid_to_add}...")
    
    # Shudhu add korar shomoy name fetch korar jonno API call hobe
    api_response = await fetch_player_data(uid_to_add)

    if api_response and 'PlayerNickname' in api_response and api_response['PlayerNickname'] != "Unknown":
        player_name = api_response.get("PlayerNickname", "Unknown")
        
        today = date.today()
        expiry_date = today + timedelta(days=days_to_add)
        expiry_date_str = expiry_date.strftime("%Y-%m-%d")

        if uids_data:
            next_serial = max(user["serial"] for user in uids_data) + 1
        else:
            next_serial = 1
            
        new_user = {
            "serial": next_serial,
            "uid": uid_to_add,
            "name": player_name,
            "expiry_date": expiry_date_str 
        }
        
        uids_data.append(new_user)
        save_uids(uids_data)
        
        reply_msg = (
            f"Successfully added!\n"
            f"Serial: {next_serial}\n"
            f"Name: {player_name}\n"
            f"UID: {uid_to_add}\n"
            f"Expires on: {expiry_date_str} ({days_to_add} days from now)\n"
        )
        
        if api_response.get("status") == 1:
            reply_msg += f"Initial like given: {api_response.get('LikesGivenByAPI', 'N/A')}"
        else:
            reply_msg += f"Warning: Name fetched, but initial like failed. (Error: {api_response.get('error', 'N/A')})"
            
        await update.message.reply_text(reply_msg)
        
    else:
        error_msg = api_response.get('error', 'API returned invalid status or Unknown player')
        await update.message.reply_text(f"Failed to add UID {uid_to_add}. API response: {error_msg}")

async def remove_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Serial number diye UID remove korar command."""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    try:
        serial_to_remove = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Wrong format. Use: /remove <Serial Number>")
        return

    uids_data = load_uids()
    user_to_remove = None

    for user in uids_data:
        if user["serial"] == serial_to_remove:
            user_to_remove = user
            break

    if user_to_remove:
        uids_data.remove(user_to_remove)
        save_uids(uids_data)
        await update.message.reply_text(
            f"Successfully removed Serial {serial_to_remove} (Name: {user_to_remove['name']}, UID: {user_to_remove['uid']})."
        )
    else:
        await update.message.reply_text(f"Error: Serial number {serial_to_remove} not found.")

async def extend_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kono UID-er meyed (validity) baranor command. (EI FUNCTION-E API CALL HOY NA)"""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    try:
        serial_to_extend = int(context.args[0])
        days_to_add = int(context.args[1])
        if days_to_add <= 0:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text("Wrong format. Use: /extend <Serial> <days>\nExample: /extend 5 15")
        return

    uids_data = load_uids()
    user_to_extend = None

    for user in uids_data:
        if user["serial"] == serial_to_extend:
            user_to_extend = user
            break

    if user_to_extend:
        # Kono API call kora hocche na. Shudhu JSON file update hobe.
        try:
            current_expiry_date_str = user_to_extend.get("expiry_date", date.today().strftime("%Y-%m-%d"))
            current_expiry_date = datetime.strptime(current_expiry_date_str, "%Y-%m-%d").date()
            
            start_date = max(date.today(), current_expiry_date)
            
            new_expiry_date = start_date + timedelta(days=days_to_add)
            new_expiry_date_str = new_expiry_date.strftime("%Y-%m-%d")
            
            user_to_extend["expiry_date"] = new_expiry_date_str
            save_uids(uids_data)
            
            await update.message.reply_text(
                f"Successfully extended! (No API Call)\n"
                f"Serial: {user_to_extend['serial']} (Name: {user_to_extend['name']})\n"
                f"New Expiry Date: {new_expiry_date_str}"
            )
        except Exception as e:
            await update.message.reply_text(f"Error updating date: {e}")
    else:
        await update.message.reply_text(f"Error: Serial number {serial_to_extend} not found.")


async def list_uids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shob saved UID-er list dekhabe (expiry date shoho)."""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    uids_data = load_uids()
    if not uids_data:
        await update.message.reply_text("No UIDs saved yet. Use /add <uid> <days> to add one.")
        return

    message = "Saved UID List:\n\n"
    today = date.today()
    
    for user in uids_data:
        expiry_date_str = user.get("expiry_date", "N/A")
        status = "Expired"
        if expiry_date_str != "N/A":
            try:
                expiry_date_obj = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
                if expiry_date_obj >= today:
                    days_left = (expiry_date_obj - today).days
                    status = f"Active ({days_left} days left)"
            except ValueError:
                status = "Invalid Date"
                
        message += f"S: {user['serial']} | Name: {user['name']}\n"
        message += f"  UID: {user['uid']}\n"
        message += f"  Expires: {expiry_date_str} ({status})\n\n"
    
    await update.message.reply_text(message)


async def process_like_queue(context: ContextTypes.DEFAULT_TYPE, chat_id: int, uids_list: list):
    """Asol like pathanor process. 10ta kore batch korbe ar 30min wait korbe."""
    
    total_uids = len(uids_list)
    
    for i in range(0, total_uids, 10):
        chunk = uids_list[i:i+10]
        batch_num = (i // 10) + 1
        total_batches = (total_uids + 9) // 10
        
        await context.bot.send_message(
            chat_id, 
            f"Processing Batch {batch_num}/{total_batches} (UIDs {i+1} to {min(i+10, total_uids)})..."
        )
        
        tasks = [fetch_player_data(user['uid']) for user in chunk]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        report_message = f"Batch {batch_num} Report:\n"
        success_count = 0
        fail_count = 0
        
        for user, result in zip(chunk, results):
            if isinstance(result, Exception):
                report_message += f"S: {user['serial']} ({user['name']}) - FAILED (Exception: {result})\n"
                fail_count += 1
            elif result and result.get("status") == 1:
                report_message += (
                    f"S: {user['serial']} ({user['name']}) - SUCCESS\n"
                    f"  Likes Given: {result.get('LikesGivenByAPI', 'N/A')}\n"
                    f"  Total Likes: {result.get('LikesafterCommand', 'N/A')}\n"
                )
                success_count += 1
            else:
                error_msg = result.get('error', 'Unknown Error')
                report_message += f"S: {user['serial']} ({user['name']}) - FAILED (API Error: {error_msg})\n"
                fail_count += 1
        
        report_message += f"\nBatch Summary: {success_count} Success, {fail_count} Failed."
        await context.bot.send_message(chat_id, report_message)
        
        if i + 10 < total_uids:
            await context.bot.send_message(
                chat_id, 
                "Batch complete. Waiting 30 minutes before next batch..."
            )
            await asyncio.sleep(30 * 60) # 30 min wait
            await context.bot.send_message(chat_id, "Waking up for next batch...")

    await context.bot.send_message(chat_id, "All batches completed. Like process finished.")


# --- Auto-Delete Helper Function ---
def cleanup_expired_uids() -> list:
    """
    Expired UID-gulo check korbe, file theke delete korbe,
    ebong delete kora UID-gulor ekta list return korbe.
    """
    logger.info("Running daily cleanup of expired UIDs...")
    all_uids = load_uids()
    valid_uids_to_keep = []
    deleted_uids_info = []
    today = date.today()
    
    if not all_uids:
        return [] 

    for user in all_uids:
        expiry_date_str = user.get("expiry_date")
        if not expiry_date_str:
            valid_uids_to_keep.append(user) 
            continue
        
        try:
            expiry_date_obj = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            if expiry_date_obj < today:
                deleted_uids_info.append(user)
            else:
                valid_uids_to_keep.append(user)
        except ValueError:
            logger.warning(f"Invalid date format for UID {user['uid']}: {expiry_date_str}. Keeping it.")
            valid_uids_to_keep.append(user) 
    
    if deleted_uids_info:
        logger.info(f"Auto-deleting {len(deleted_uids_info)} expired UIDs.")
        save_uids(valid_uids_to_keep) 
        return deleted_uids_info
    else:
        logger.info("No expired UIDs found to delete.")
        return []


def get_valid_uids_for_processing():
    """Shudhu active (non-expired) UID-gulo return kore."""
    all_uids = load_uids()
    valid_uids = []
    today = date.today()
    
    for user in all_uids:
        expiry_date_str = user.get("expiry_date")
        if not expiry_date_str:
            continue 
        
        try:
            expiry_date_obj = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            if expiry_date_obj >= today:
                valid_uids.append(user) 
        except ValueError:
            logger.warning(f"Invalid date format for UID {user['uid']}: {expiry_date_str}")
            
    return valid_uids

async def send_likes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /m command. Shudhu *valid* UID-gulote like pathabe. """
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    if processing_lock.locked():
        await update.message.reply_text("A process is already running. Please wait.")
        return

    valid_uids_list = get_valid_uids_for_processing()
    
    if not valid_uids_list:
        await update.message.reply_text("No valid (non-expired) UIDs found to process.")
        return

    async with processing_lock:
        await update.message.reply_text(
            f"Starting MANUAL like process for {len(valid_uids_list)} valid users..."
        )
        await process_like_queue(context, update.effective_chat.id, valid_uids_list)


# --- NOTUN COMMAND: /settime ---
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Automatic job-er time set korbe ebong job-ti reschedule korbe."""
    if not is_admin_in_allowed_group(update):
        if update.effective_chat.id == ALLOWED_GROUP_ID:
             await update.message.reply_text("Sorry, shudhu Admin ei command use korte parbe.")
        return

    try:
        time_str = context.args[0]
        new_hour, new_minute = map(int, time_str.split(':'))
        
        # Test if time is valid
        new_run_time = time(hour=new_hour, minute=new_minute, tzinfo=BD_TIMEZONE)
        
    except (IndexError, ValueError):
        await update.message.reply_text("Wrong format. Use: /settime <HH:MM> (24-hour format)\nExample: /settime 7:00 (Sokal 7ta) or /settime 22:30 (Raat 10:30)")
        return

    # --- Reschedule the job ---
    job_name = "daily-like-job"
    
    # 1. Purono job remove kora
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if not current_jobs:
         await update.message.reply_text("Error: Could not find the running job to reschedule. Restarting the bot might fix this.")
         return
         
    for job in current_jobs:
        job.schedule_removal()
        logger.info(f"Removed old job: {job_name}")

    # 2. Notun time diye notun job add kora
    context.job_queue.run_daily(
        scheduled_like_job, 
        time=new_run_time, 
        data={"chat_id": ALLOWED_GROUP_ID}, 
        name=job_name
    )
    logger.info(f"Scheduled new job '{job_name}' at {new_run_time.strftime('%H:%M')}")

    # 3. Notun time config file-e save kora
    config = load_config()
    config["scheduled_hour"] = new_hour
    config["scheduled_minute"] = new_minute
    save_config(config)

    await update.message.reply_text(
        f"Successfully updated automatic job time!\n"
        f"Notun schedule: Protidin {new_hour}:{new_minute:02d} (Bangladesh Time)."
    )


# --- Automatic Scheduled Job (Auto-Delete Shoho) ---
async def scheduled_like_job(context: ContextTypes.DEFAULT_TYPE):
    """Ei function-ti protidin nirdishto shomoye automatic call hobe."""
    
    chat_id = context.job.data["chat_id"]
    
    logger.info("Running scheduled daily job...")

    # --- AUTO-DELETE SECTION START ---
    try:
        deleted_users = cleanup_expired_uids()
        if deleted_users:
            report_msg = "Expired UID Auto-Delete Report:\n"
            for user in deleted_users:
                report_msg += f" - Deleted: {user['name']} (UID: {user['uid']}, Expired: {user['expiry_date']})\n"
            await context.bot.send_message(chat_id, report_msg)
    except Exception as e:
        logger.error(f"Error during expired UID cleanup: {e}")
        await context.bot.send_message(chat_id, f"Error during auto-delete process: {e}")
    # --- AUTO-DELETE SECTION END ---

    if processing_lock.locked():
        logger.warning("Scheduled job tried to run, but a process was already locked.")
        await context.bot.send_message(chat_id, "Scheduled job wanted to start, but another process is already running. Skipping this cycle.")
        return

    valid_uids_list = get_valid_uids_for_processing() 
    
    if not valid_uids_list:
        logger.info("Scheduled job: No valid UIDs to process today.")
        await context.bot.send_message(chat_id, "Automatic Job: No valid (non-expired) UIDs found to process today.")
        return

    async with processing_lock:
        logger.info(f"Scheduled job: Starting process for {len(valid_uids_list)} valid users.")
        await context.bot.send_message(
            chat_id,
            f"Starting AUTOMATIC scheduled like process for {len(valid_uids_list)} valid users..."
        )
        await process_like_queue(context, chat_id, valid_uids_list)

# -------------------------------------

def main():
    """Bot-ti run korbe ebong job schedule korbe."""
    if BOT_TOKEN.startswith("YOUR_") or ADMIN_USER_ID == 0 or ALLOWED_GROUP_ID == 0:
        print("CRITICAL ERROR: BOT_TOKEN, ADMIN_USER_ID, and ALLOWED_GROUP_ID must be set!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # --- Job Queue Setup (UPDATE KORA) ---
    job_queue = application.job_queue
    
    # 1. Config file theke time load kora
    config = load_config()
    scheduled_hour = config.get("scheduled_hour", DEFAULT_SCHEDULED_HOUR_BD)
    scheduled_minute = config.get("scheduled_minute", DEFAULT_SCHEDULED_MINUTE_BD)
    
    # Nirdishto shomoy-ti setup kora (BD Timezone-e)
    run_time = time(hour=scheduled_hour, minute=scheduled_minute, tzinfo=BD_TIMEZONE)
    
    job_queue.run_daily(
        scheduled_like_job, 
        time=run_time, 
        data={"chat_id": ALLOWED_GROUP_ID}, 
        name="daily-like-job" # Ei name-ti khub important
    )
    # ------------------------------

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_uid))
    application.add_handler(CommandHandler("remove", remove_uid))
    application.add_handler(CommandHandler("extend", extend_uid)) 
    application.add_handler(CommandHandler("list", list_uids))
    application.add_handler(CommandHandler("m", send_likes_command))
    application.add_handler(CommandHandler("settime", set_time)) # <-- Notun handler add kora

    # Bot-ti run kora
    print(f"Bot is running... Admin: {ADMIN_USER_ID}, Group: {ALLOWED_GROUP_ID}")
    print(f"Automatic job scheduled daily at {scheduled_hour}:{scheduled_minute:02d} (Asia/Dhaka time) [Loaded from config/default]") # <-- Updated
    application.run_polling()


# --- Code-er Shesh Ongsho (Indentation Error Fix) ---
# Agamito apnar 'SyntaxError' ebong 'IndentationError' ekhane hocchilo.
# Nicher duiti line-i shothik format-e dewa holo.
if __name__ == "__main__":
    # <-- Shothik Niyom: Ei 'main()' line-tir age obosshoi 4-ti space (ba 1-ta Tab) thakte hobe
    main()
