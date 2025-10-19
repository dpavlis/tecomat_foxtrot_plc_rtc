# Tecomat PLC RTC Synchronization Tool

A Python utility for setting the Real-Time Clock (RTC) on Tecomat FOXTROT PLC controllers using the EPSNET UDP protocol.

## Overview

This tool implements the EPSNET UDP protocol to communicate with Tecomat PLCs and update their internal real-time clock. It supports both current time synchronization and setting specific date/time values via command-line interface.

**Supported PLCs:**
- Tecomat FOXTROT 2 series
- Tecomat TC800 series
- Any Tecomat PLC with EPSNET UDP support on communication channels in PC mode

## Features

- ✅ Set PLC clock to current system time
- ✅ Set PLC clock to specific date and time
- ✅ Automatic timezone offset support
- ✅ Response verification with 0xE5 acknowledgement
- ✅ Detailed logging and error handling
- ✅ Command-line interface for easy automation
- ✅ Full EPSNET UDP protocol implementation
- ✅ Verified against official Tecomat documentation

## Installation

### Requirements

- Python 3.6 or higher
- Network access to Tecomat PLC

### Install

```bash
# Clone the repository
git clone https://github.com/yourusername/tecomat-rtc-sync.git
cd tecomat-rtc-sync

# No additional dependencies required (uses only Python standard library)
```

## Usage

### Basic Usage

```bash
# Set RTC to current time
python tecomat_rtc.py

# Set RTC to specific time (today)
python tecomat_rtc.py --time 14:30:00

# Set RTC to specific date and time
python tecomat_rtc.py --time 14:30:00 --date 2025-10-17

# Use custom PLC IP address
python tecomat_rtc.py --ip 192.168.1.100 --time 08:00:00
```

### Advanced Options

```bash
# Apply timezone offset (e.g., if PLC uses UTC+2)
python tecomat_rtc.py --time 20:00:00 --timezone-offset 2
# This will set PLC clock to 22:00:00 (20:00 + 2 hours)

# Skip response verification (faster, but no confirmation)
python tecomat_rtc.py --time 12:00:00 --no-verify

# Custom timeout for slow networks
python tecomat_rtc.py --time 15:30:00 --timeout 5.0

# Use custom ports
python tecomat_rtc.py --port 61682 --local-port 64481
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--time HH:MM:SS` | Time to set (24-hour format) | Current time |
| `--date YYYY-MM-DD` | Date to set | Current date |
| `--ip ADDRESS` | PLC IP address | 192.168.11.50 |
| `--port PORT` | PLC UDP port | 61682 |
| `--local-port PORT` | Local UDP port | 64481 |
| `--timezone-offset HOURS` | Hours to add to specified time | 0 |
| `--no-offset` | Same as `--timezone-offset 0` | - |
| `--no-verify` | Don't wait for PLC acknowledgement | False |
| `--timeout SECONDS` | Response timeout | 2.0 |
| `--help` | Show help message | - |

## Examples

### Example 1: Daily Sync via Cron

Synchronize PLC clock daily at 2 AM:

```bash
# Add to crontab
0 2 * * * /usr/bin/python3 /path/to/tecomat_rtc.py --ip 192.168.1.50
```

### Example 2: Set Specific Time

Set PLC to midnight on New Year:

```bash
python tecomat_rtc.py --date 2026-01-01 --time 00:00:00
```

### Example 3: Timezone Adjustment

If your PLC stores time in UTC+2 and your local time is UTC+0:

```bash
python tecomat_rtc.py --timezone-offset 2
```

### Example 4: Automation Script

```bash
#!/bin/bash
# sync_plc_clocks.sh - Sync multiple PLCs

PLCS=("192.168.1.50" "192.168.1.51" "192.168.1.52")

for plc in "${PLCS[@]}"; do
    echo "Syncing PLC at $plc..."
    python3 tecomat_rtc.py --ip "$plc" --timeout 5.0
done
```

## Protocol Details

This implementation uses the **EPSNET UDP protocol** as specified in Tecomat documentation (TXV 004 69.01, section 5.4 and 5.6.2).

### Packet Structure

**Command Packet (24 bytes):**
```
UDP Header (6 bytes):
  [MESI] [PN] [Reserved] [DPLEN]

EPSNET Message (18 bytes):
  68 0B 0B 68 [DA] [SA] 63 08 [TIME-7B] [FCS] 16 00
  │  │  │  │   │    │   │  │   └─Time   └─CS └─ED,Pad
  │  │  │  │   │    │   │  └─RB (Request Byte = 8)
  │  │  │  │   │    │   └─FC (Function Code = 0x63 SETTID)
  │  │  │  │   │    └─SA (Source Address)
  │  │  │  │   └─DA (Destination Address = 0)
  │  │  │  └─SD2R (Start Delimiter 2 Repeat)
  │  │  └─LER (Length Repeat)
  │  └─LE (Length = 11)
  └─SD2 (Start Delimiter 2)
```

**Response Packet (7 bytes):**
```
UDP Header (6 bytes):
  [MESI] [PN] [Reserved] [DPLEN=1]

EPSNET Response (1 byte):
  E5 = Success (SAC - Short Acknowledge)
```

### Time Format (7 bytes)

| Byte | Description | Range | Example |
|------|-------------|-------|---------|
| 0 | Year (since 2000) | 0-99 | 25 (=2025) |
| 1 | Month | 1-12 | 10 (October) |
| 2 | Day | 1-31 | 17 |
| 3 | Hour | 0-23 | 14 |
| 4 | Minute | 0-59 | 30 |
| 5 | Second | 0-59 | 45 |
| 6 | Day of Week | 1-7 | 5 (Friday) |

**Day of Week Encoding:**
- 1 = Monday (pondělí)
- 2 = Tuesday (úterý)
- 3 = Wednesday (středa)
- 4 = Thursday (čtvrtek)
- 5 = Friday (pátek)
- 6 = Saturday (sobota)
- 7 = Sunday (neděle)

### Checksum Calculation

```python
# FCS (Frame Check Sum)
checksum = (sum_of_RB_and_TIME_bytes - 0x20) & 0xFF
```

Where:
- RB = 0x08 (1 byte)
- TIME = 7 bytes (year, month, day, hour, minute, second, dow)

## Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0xE5 | Success (SAC) | RTC updated successfully |
| 0x02 | Unknown service | Check PLC firmware version |
| 0x03 | Service not activated | Enable PC mode on PLC |
| 0x04 | Service blocked by password | Remove password protection |
| 0x09 | Data not yet available | Retry later |
| 0x0C | Invalid parameters | Check time/date values |
| (none) | Timeout | Check network connectivity |

## Troubleshooting

### PLC Not Responding

1. **Check network connectivity:**
   ```bash
   ping 192.168.11.50
   ```

2. **Verify PLC port is accessible:**
   ```bash
   # On Linux/Mac:
   nc -u -v 192.168.11.50 61682
   
   # On Windows:
   Test-NetConnection -ComputerName 192.168.11.50 -Port 61682
   ```

3. **Ensure PLC communication channel is in PC mode** (not PLC mode)

4. **Check firewall rules** - UDP port 61682 must be open

### Wrong Time Set

1. **Check timezone offset:**
   - If PLC shows time 2 hours ahead, use `--timezone-offset -2`
   - If PLC shows time 2 hours behind, use `--timezone-offset 2`

2. **Verify system time is correct:**
   ```bash
   date
   ```

### Permission Denied

On Linux/Mac, binding to ports < 1024 requires root:

```bash
# If using port < 1024:
sudo python3 tecomat_rtc.py

# Or use default ports (no sudo needed)
python3 tecomat_rtc.py
```

## Technical Reference

### Documentation

This implementation is based on official Tecomat documentation:
- **Document**: TXV 004 69.01 - "Sériová komunikace PLC TECOMAT FOXTROT 2 a TC800"
- **Protocol**: EPSNET (section 5)
- **UDP Extension**: EPSNET UDP/TCP (section 5.4)
- **SETTID Command**: Section 5.6.2

### Network Capture Analysis

The implementation was developed by analyzing actual EPSNET UDP traffic between Tecomat software and PLC controllers, then verified against official protocol documentation.

### Compatible Software

This tool provides the same RTC synchronization functionality as:
- Tecomat Mosaic (development environment)
- TecoRoute (SCADA/HMI software)
- Reliance (SCADA system)

## Development

### Running Tests

```bash
# Test with local PLC
python tecomat_rtc.py --ip 192.168.1.50 --time 12:00:00

# Test with verbose output (modify script to add debug=True)
# Check response payload and timing
```

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test with actual Tecomat hardware
4. Submit a pull request

### Protocol Extensions

The EPSNET protocol supports many other commands:
- READN - Read from PLC memory
- WRITEN - Write to PLC memory
- GETSW - Read status word
- GETERR - Read error stack

These could be added in future versions.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is provided as-is without any warranty. Always test in a non-production environment first. The author is not responsible for any damage or data loss caused by using this software.

## Acknowledgments

- Based on Tecomat EPSNET protocol specification
- Developed through network traffic analysis and protocol documentation review
- Thanks to Teco a.s. for comprehensive protocol documentation

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Check Tecomat official documentation: https://www.tecomat.com
- Contact: [Your contact information]

## Changelog

### v1.0.0 (2025-10-17)
- Initial release
- SETTID command implementation
- Command-line interface
- Response verification
- Timezone offset support
- Verified against official documentation

---

**Made with ❤️ for the Tecomat PLC community**