import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_last_rotation_time = 0.0
_rotation_lock = asyncio.Lock()

async def rotate_warp_proxy(cooldown_seconds: int = 15) -> bool:
    """
    Safely re-registers Cloudflare WARP proxy to obtain a fresh egress IP / session.
    Protected by lock and cooldown to prevent race conditions from concurrent requests.
    """
    global _last_rotation_time
    async with _rotation_lock:
        now = time.time()
        if now - _last_rotation_time < cooldown_seconds:
            logger.info(f"[WARP] Skipped rotation: performed {now - _last_rotation_time:.1f}s ago (cooldown {cooldown_seconds}s)")
            await asyncio.sleep(2)
            return True
            
        logger.warning("[WARP] Initiating Cloudflare WARP rotation...")
        commands = [
            ["warp-cli", "--accept-tos", "registration", "delete"],
            ["warp-cli", "--accept-tos", "registration", "new"],
            ["warp-cli", "--accept-tos", "mode", "proxy"],
            ["warp-cli", "--accept-tos", "proxy", "port", "40000"],
            ["warp-cli", "--accept-tos", "connect"],
        ]
        
        for cmd in commands:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.error(f"[WARP] Command {' '.join(cmd)} failed (code {proc.returncode}): {stderr.decode()}")
            except Exception as e:
                logger.error(f"[WARP] Error executing {' '.join(cmd)}: {e}")
                return False
                
        _last_rotation_time = time.time()
        logger.info("[WARP] WARP proxy successfully rotated and reconnected on port 40000.")
        await asyncio.sleep(2)
        return True

def is_geo_blocked_error(error: Exception) -> bool:
    """Check if an exception is related to Google Gemini location / geo-blocking."""
    e_str = str(error)
    return "User location is not supported" in e_str or "FAILED_PRECONDITION" in e_str
