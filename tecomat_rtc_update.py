#!/usr/bin/env python3
"""
Tecomat PLC Real-Time Clock (RTC) Update Script

This script sends UDP packets to update the RTC in a Tecomat PLC controller.
Based on network capture analysis of communication between PLC and control software.

Protocol structure (UDP payload):
- Tecomat protocol header
- RTC command: 0x63
- Data length: 0x08 (8 bytes)
- Year (since 2000)
- Month (1-12)
- Day (1-31)
- Hour (0-23)
- Minute (0-59)
- Second (0-59)
- Day of week (0=Sunday, 1=Monday, ..., 6=Saturday)
- Checksum (sum of 8 RTC bytes - 0x20)

Usage:
    python script.py                          # Set to current time
    python script.py --time 14:30:00          # Set to specific time today
    python script.py --time 14:30:00 --date 2025-10-17  # Set to specific date and time
    python script.py --help                   # Show help
"""

import socket
import struct
from datetime import datetime, timedelta
import time
import argparse
import sys

class TecomatRTC:
    """Tecomat PLC RTC updater"""
    
    # Protocol constants
    RTC_COMMAND = 0x63  # Set RTC command
    DATA_LENGTH = 0x08  # 8 bytes of RTC data
    
    def __init__(self, plc_ip: str, plc_port: int = 61682, local_port: int = 64481):
        """
        Initialize Tecomat RTC updater
        
        Args:
            plc_ip: PLC IP address (e.g., '192.168.11.50')
            plc_port: PLC UDP port (default: 61682 / 0xF0F2)
            local_port: Local UDP port (default: 64481 / 0xFBE1)
        """
        self.plc_ip = plc_ip
        self.plc_port = plc_port
        self.local_port = local_port
        self.sock = None
        
    def _calculate_checksum(self, data_bytes: list) -> int:
        """
        Calculate checksum for RTC data
        
        The checksum algorithm for Tecomat RTC command:
        Checksum = (sum of all 8 RTC data bytes) - 0x20
        
        Args:
            data_bytes: List of RTC data bytes (length, year, month, day, hour, min, sec, dow)
            
        Returns:
            Checksum byte (0x00-0xFF)
        """
        # Sum all data bytes and subtract 0x20
        total = sum(data_bytes)
        checksum = (total - 0x20) & 0xFF
        return checksum
    
    def _build_rtc_packet(self, dt: datetime) -> bytes:
        """
        Build complete RTC update packet
        
        Args:
            dt: datetime object with the time to set
            
        Returns:
            Complete UDP payload as bytes
        """
        # Extract time components
        year = dt.year - 2000  # Years since 2000
        month = dt.month
        day = dt.day
        hour = dt.hour
        minute = dt.minute
        second = dt.second
        # Day of week: Monday=1, Tuesday=2, ..., Sunday=7 (per EPSNET documentation)
        dow = dt.weekday() + 1  # Python weekday() returns 0=Monday, so add 1
        
        # Validate ranges
        if not (0 <= year <= 99):
            raise ValueError(f"Year out of range: {dt.year} (must be 2000-2099)")
        if not (1 <= month <= 12):
            raise ValueError(f"Month out of range: {month}")
        if not (1 <= day <= 31):
            raise ValueError(f"Day out of range: {day}")
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour out of range: {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute out of range: {minute}")
        if not (0 <= second <= 59):
            raise ValueError(f"Second out of range: {second}")
        
        # Build RTC data (8 bytes after command)
        rtc_data = [
            self.DATA_LENGTH,  # Length byte
            year,
            month,
            day,
            hour,
            minute,
            second,
            dow
        ]
        
        # Calculate checksum
        checksum = self._calculate_checksum(rtc_data)
        
        # Build complete Tecomat protocol payload
        # Protocol header (from captured packets)
        header = [
            0x02, 0x01, 0x02, 0x00, 0x00,  # Protocol header
            0x11,                           # Packet type/length indicator
            0x68, 0x0b, 0x0b,              # Protocol markers
            0x68, 0x00, 0x7d               # More protocol bytes
        ]
        
        # Complete payload: header + RTC command + data + checksum + footer
        payload = header + [self.RTC_COMMAND] + rtc_data + [checksum, 0x16, 0x00]
        
        return bytes(payload)
    
    def connect(self):
        """Create and bind UDP socket"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', self.local_port))
        print(f"UDP socket bound to port {self.local_port}")
    
    def close(self):
        """Close UDP socket"""
        if self.sock:
            self.sock.close()
            self.sock = None
            print("Socket closed")
    
    def _parse_response(self, response: bytes) -> dict:
        """
        Parse PLC response packet
        
        Args:
            response: Raw response bytes (UDP payload only, headers stripped by socket)
            
        Returns:
            Dictionary with parsed response info
        """
        if len(response) < 6:
            return {
                'success': False,
                'error': f'Response too short ({len(response)} bytes)',
                'raw': response.hex(' ')
            }
        
        # Python socket receives only UDP payload (no Ethernet/IP/UDP headers)
        # Expected response: 02 01 02 00 00 01 E5 00 (8 bytes)
        # But we might receive variations, minimum expected is 6 bytes
        payload = response
        
        # Check for success indicator (0xE5)
        # The 0xE5 byte should be at position 6 (0-indexed) in full response,
        # but could vary. Let's check if 0xE5 exists anywhere in response
        if 0xE5 in payload:
            e5_pos = payload.index(0xE5)
            return {
                'success': True,
                'status_code': 0xE5,
                'e5_position': e5_pos,
                'payload': payload.hex(' '),
                'length': len(payload),
                'raw': response.hex(' ')
            }
        else:
            return {
                'success': False,
                'error': f'No 0xE5 ACK found in response',
                'payload': payload.hex(' '),
                'length': len(payload),
                'raw': response.hex(' ')
            }
    
    def set_rtc(self, dt: datetime = None, timezone_offset: int = 0, 
                timeout: float = 2.0, verify: bool = True) -> bool:
        """
        Send RTC update packet to PLC
        
        Args:
            dt: datetime to set (default: current time)
            timezone_offset: Timezone offset in hours (e.g., +2 for UTC+2)
            timeout: Response timeout in seconds (default: 2.0)
            verify: Wait for and verify response (default: True)
            
        Returns:
            True if packet was sent successfully and ACK received (if verify=True)
        """
        if dt is None:
            dt = datetime.now()
        
        # Store original time for logging
        original_dt = dt
        
        # Apply timezone offset if specified
        if timezone_offset != 0:
            from datetime import timedelta
            dt = dt + timedelta(hours=timezone_offset)
            print(f"ℹ️  Timezone offset applied: {timezone_offset}h")
            print(f"   Original time: {original_dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Adjusted time: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            if not self.sock:
                self.connect()
            
            # Build packet
            packet = self._build_rtc_packet(dt)
            
            # Send packet
            self.sock.sendto(packet, (self.plc_ip, self.plc_port))
            
            print(f"\n📤 RTC update sent to {self.plc_ip}:{self.plc_port}")
            print(f"   Time set to: {dt.strftime('%Y-%m-%d %H:%M:%S')} (DOW: {dt.strftime('%A')})")
            print(f"   Packet ({len(packet)} bytes): {packet.hex(' ')}")
            
            # Decode packet for verification
            if len(packet) >= 21:
                print(f"   Decoded: Year={packet[14]}, Month={packet[15]}, Day={packet[16]}, " +
                      f"Hour={packet[17]}, Min={packet[18]}, Sec={packet[19]}, DOW={packet[20]}")
            
            # Wait for response
            if verify:
                self.sock.settimeout(timeout)
                try:
                    response, addr = self.sock.recvfrom(1024)
                    print(f"\n📥 Response received from {addr[0]} ({len(response)} bytes)")
                    print(f"   Raw response: {response.hex(' ')}")
                    
                    # Parse response
                    result = self._parse_response(response)
                    
                    if result['success']:
                        print(f"   ✅ SUCCESS: PLC acknowledged RTC update (status: 0xE5)")
                        print(f"   Response payload: {result['payload']}")
                        if 'e5_position' in result:
                            print(f"   0xE5 found at byte position {result['e5_position']}")
                        return True
                    else:
                        print(f"   ❌ FAILED: {result['error']}")
                        print(f"   Response: {result.get('payload', 'N/A')}")
                        return False
                        
                except socket.timeout:
                    print(f"   ⚠️  WARNING: No response received within {timeout}s (timeout)")
                    print("   RTC update may have succeeded, but no ACK was received")
                    return False
            else:
                print("   ℹ️  Verification skipped (verify=False)")
                return True
                
        except Exception as e:
            print(f"❌ Error sending RTC update: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def periodic_update(self, interval: int = 60, timezone_offset: int = 0):
        """
        Periodically update PLC RTC
        
        Args:
            interval: Update interval in seconds
            timezone_offset: Timezone offset in hours
        """
        print(f"Starting periodic RTC updates every {interval} seconds")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                self.set_rtc(timezone_offset=timezone_offset)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopping periodic updates")
        finally:
            self.close()


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Update Tecomat PLC Real-Time Clock',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Set RTC to current time (no offset)
  %(prog)s --time 14:30:00                    # Set time to 14:30:00 today (no offset)
  %(prog)s --time 14:30:00 --timezone-offset 2  # Set to 14:30 + 2h = 16:30
  %(prog)s --time 14:30:00 --date 2025-10-17  # Set specific date and time
  %(prog)s --ip 192.168.1.100 --time 08:00:00 # Use custom PLC IP address
  
Note: By default, NO timezone offset is applied. If your PLC stores time in a 
      different timezone, use --timezone-offset to adjust (e.g., --timezone-offset 2 
      for UTC+2 will add 2 hours to the time you specify).
        """
    )
    
    parser.add_argument(
        '--time',
        type=str,
        help='Time to set in format HH:MM:SS (e.g., 14:30:00). If not specified, uses current time.'
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='Date to set in format YYYY-MM-DD (e.g., 2025-10-17). If not specified, uses current date.'
    )
    
    parser.add_argument(
        '--ip',
        type=str,
        default='192.168.11.50',
        help='PLC IP address (default: 192.168.11.50)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=61682,
        help='PLC UDP port (default: 61682)'
    )
    
    parser.add_argument(
        '--local-port',
        type=int,
        default=64481,
        help='Local UDP port (default: 64481)'
    )
    
    parser.add_argument(
        '--timezone-offset',
        type=int,
        default=0,
        help='Timezone offset in hours to ADD to the specified time (default: 0). Set to 2 if PLC expects UTC+2.'
    )
    
    parser.add_argument(
        '--no-offset',
        action='store_true',
        help='Explicitly set timezone offset to 0 (same as --timezone-offset 0)'
    )
    
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Do not wait for PLC acknowledgement'
    )
    
    parser.add_argument(
        '--timeout',
        type=float,
        default=2.0,
        help='Response timeout in seconds (default: 2.0)'
    )
    
    return parser.parse_args()


def parse_time_string(time_str):
    """
    Parse time string in format HH:MM:SS
    
    Args:
        time_str: Time string (e.g., "14:30:00")
        
    Returns:
        Tuple of (hour, minute, second)
        
    Raises:
        ValueError: If time format is invalid
    """
    try:
        parts = time_str.split(':')
        if len(parts) != 3:
            raise ValueError("Time must be in format HH:MM:SS")
        
        hour = int(parts[0])
        minute = int(parts[1])
        second = int(parts[2])
        
        if not (0 <= hour <= 23):
            raise ValueError(f"Hour must be 0-23, got {hour}")
        if not (0 <= minute <= 59):
            raise ValueError(f"Minute must be 0-59, got {minute}")
        if not (0 <= second <= 59):
            raise ValueError(f"Second must be 0-59, got {second}")
        
        return (hour, minute, second)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid time format '{time_str}': {e}")


def parse_date_string(date_str):
    """
    Parse date string in format YYYY-MM-DD
    
    Args:
        date_str: Date string (e.g., "2025-10-17")
        
    Returns:
        Tuple of (year, month, day)
        
    Raises:
        ValueError: If date format is invalid
    """
    try:
        parts = date_str.split('-')
        if len(parts) != 3:
            raise ValueError("Date must be in format YYYY-MM-DD")
        
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2])
        
        if not (2000 <= year <= 2099):
            raise ValueError(f"Year must be 2000-2099, got {year}")
        if not (1 <= month <= 12):
            raise ValueError(f"Month must be 1-12, got {month}")
        if not (1 <= day <= 31):
            raise ValueError(f"Day must be 1-31, got {day}")
        
        # Validate the date is actually valid
        datetime(year, month, day)
        
        return (year, month, day)
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid date format '{date_str}': {e}")


def main():
    """Main function with command line argument support"""
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Build target datetime
    target_dt = None
    
    try:
        if args.time or args.date:
            # Start with current date/time
            now = datetime.now()
            
            # Parse date if provided
            if args.date:
                year, month, day = parse_date_string(args.date)
            else:
                year, month, day = now.year, now.month, now.day
            
            # Parse time if provided
            if args.time:
                hour, minute, second = parse_time_string(args.time)
            else:
                hour, minute, second = now.hour, now.minute, now.second
            
            # Create target datetime
            target_dt = datetime(year, month, day, hour, minute, second)
            print(f"Target time: {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            # Use current time
            target_dt = datetime.now()
            print(f"Using current time: {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    # Determine timezone offset
    tz_offset = 0 if args.no_offset else args.timezone_offset
    
    # Create RTC updater
    rtc = TecomatRTC(args.ip, args.port, args.local_port)
    
    try:
        print(f"\n{'='*60}")
        print(f"Tecomat PLC RTC Update")
        print(f"{'='*60}")
        print(f"PLC Address: {args.ip}:{args.port}")
        print(f"Target Time (before offset): {target_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        if tz_offset != 0:
            adjusted_dt = target_dt + timedelta(hours=tz_offset)
            print(f"Timezone Offset: {'+' if tz_offset >= 0 else ''}{tz_offset}h")
            print(f"Time sent to PLC: {adjusted_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"Timezone Offset: None (sending time as-is)")
        print(f"Verification: {'Enabled' if not args.no_verify else 'Disabled'}")
        print(f"{'='*60}\n")
        
        # Set RTC
        success = rtc.set_rtc(
            dt=target_dt,
            timezone_offset=tz_offset,
            timeout=args.timeout,
            verify=not args.no_verify
        )
        
        if success:
            print(f"\n{'='*60}")
            print("✅ RTC UPDATE SUCCESSFUL")
            print(f"{'='*60}")
            sys.exit(0)
        else:
            print(f"\n{'='*60}")
            print("❌ RTC UPDATE FAILED")
            print(f"{'='*60}")
            print("\nTroubleshooting:")
            print("1. Check if PLC IP address is correct (use --ip)")
            print("2. Verify network connectivity to PLC")
            print("3. Check if timezone offset is correct (default is 0, no offset)")
            print("4. Check PLC documentation for correct ports")
            print("5. Try increasing timeout with --timeout 5.0")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        rtc.close()


# Keep the old main for backwards compatibility
def main_example():
    """Example usage (original main function)"""
    
    # Configuration
    PLC_IP = "192.168.11.50"      # Change to your PLC IP address
    PLC_PORT = 61682               # 0xF0F2
    LOCAL_PORT = 64481             # 0xFBE1
    
    # IMPORTANT: Based on capture analysis, the PLC seems to store time in UTC+2
    # If your local time is 20:29, the PLC expects 22:29 (20:29 + 2 hours)
    # Set to 0 if you want to send your local time as-is
    TIMEZONE_OFFSET = 2
    
    # Create RTC updater
    rtc = TecomatRTC(PLC_IP, PLC_PORT, LOCAL_PORT)
    
    try:
        # Example 1: Set RTC to current time with timezone offset
        print("=== Setting PLC RTC to current time (with timezone offset) ===\n")
        success = rtc.set_rtc(timezone_offset=TIMEZONE_OFFSET, verify=True)
        
        if success:
            print("\n✅ RTC update completed successfully!")
        else:
            print("\n❌ RTC update failed or not acknowledged")
            print("\nTroubleshooting:")
            print("1. Check if PLC IP address is correct")
            print("2. Verify network connectivity to PLC")
            print("3. Try with timezone_offset=0 if offset is incorrect")
            print("4. Check if hour value in decoded packet is reasonable (0-23)")
        
        print("\n" + "="*50 + "\n")
        
        # Example 2: Set without timezone offset (use local time as-is)
        print("=== Setting PLC RTC with NO timezone offset ===\n")
        rtc.set_rtc(timezone_offset=0, verify=True)
        
        # Example 3: Set to specific time manually (already in PLC's timezone)
        # print("\n" + "="*50 + "\n")
        # print("=== Setting to specific time (manual control) ===\n")
        # specific_time = datetime(2025, 10, 17, 2, 30, 0)  # 2:30 AM
        # rtc.set_rtc(specific_time, timezone_offset=0, verify=True)
        
    finally:
        rtc.close()


if __name__ == "__main__":
    main()
