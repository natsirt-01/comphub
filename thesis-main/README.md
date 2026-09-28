# CompHub

CompHub is a Windows lab-monitoring system with Admin/Teacher and Student applications. The Admin/Teacher server stores accounts, sessions, activity alerts, inventory, and blocking rules in SQLite. Student computers appear in monitoring after the Student client signs in and connects; unauthenticated network presence is not enough to identify a computer or assign it to a lab.

## Accounts and Monitoring

- Admin creates teacher accounts, renames accounts, resets student passwords, manages labs and inventory, and adds or removes restricted-site keywords under **Blocking Rules**.
- Admin can register IPv4 addresses as **Student** or **Teacher** under **IP Management**. Registration is saved locally and applies to active streams immediately; removing it restores the role announced by that app.
- Students submit account registrations; Teachers approve or decline requests in **Account Approvals**.
- Students can change their own display name after verifying their current password, and can update their password in **Settings**.
- Teacher monitoring displays students assigned to the selected lab. Admin monitoring displays connected students and teachers. Lab Monitoring shows passive occupancy cards and refreshes every five seconds; right-clicking those cards does not issue commands.
- Student clients download blocking rules at startup and refresh them every 30 seconds.
- The restricted-site warning stays visible without stealing keyboard focus and disappears when the active window leaves the restricted match; it reappears when the student returns to one.
- Admin session history, Teacher history, Student history, and the Teacher activity inbox accept inclusive `YYYY-MM-DD` start/end filters.

## Install Wizard

End users run `installer-output/CompHub-Setup.exe`, select **Server**, **Student**, or both, and enter the Teacher and Admin server IPv4 addresses. The installer places the selected role under `Program Files\CompHub`, creates Start Menu shortcuts, and writes role-specific network configuration beside each executable. Server data is kept under `%ProgramData%\CompHub\scholarnet.db` so upgrades do not replace the database.

### Build the Installer

On a Windows build machine:

1. Install Python 3.11 and the project dependencies from `requirements.txt` in the repository root environment.
2. Install PyInstaller (`python -m pip install pyinstaller`) and Inno Setup 6.
3. From `thesis-main`, run `./build_installer.ps1` in PowerShell.
4. Test the generated setup on a clean Windows machine for both server and student-only installation types before distribution.

The Student executable bundles OpenCV, DeepFace, and TensorFlow, so packaging and installation can be large and may require additional PyInstaller hooks on some Python environments.

## Network Setup

The Admin host advertises itself with UDP broadcast discovery on port `37020` after an Admin signs in. Teacher clients send their LAN address to Admin when they select a lab; Student clients discover Admin and receive the online Teacher address from the server. No Admin, Teacher, or Student IP list is configured manually. Discovery is limited to the local broadcast network, so clients on another Wi-Fi/LAN cannot discover the server. Some access points enable wireless client isolation; disable that setting for the lab SSID or local clients cannot reach each other.

The setup wizard adds and removes Windows Firewall rules for UDP `37020` and TCP `5001`, `5050`, `9996`-`9999`, restricted to the local subnet. Keep the Student client installed and running on each lab PC; authenticated login and the stream handshake populate live monitoring and lab occupancy. Discovery does not identify unmanaged devices that do not run the client.

## Startup Flow

1. Connect the Admin, Teacher, and Student computers to the same local Wi-Fi/LAN. Disable wireless client isolation. When running from source, allow the app through Windows Firewall; the installer creates the local-subnet rules automatically.
2. On the Admin computer, run `thesis-main/login.py` and sign in with the Admin account. Keep it open; the Admin service begins LAN discovery after Admin authentication.
3. On the Teacher computer, run `thesis-main/login.py`, sign in with the Teacher account, and select the lab. The Teacher discovers Admin and announces its current LAN address.
4. On each Student computer, install dependencies from the workspace root with `python -m pip install -r Student/requirements.txt`, then run `Student/login_student.py`. The screen discovers Admin and lists online Teachers only. Select the Teacher and matching lab, then sign in with an approved Student account.
5. The authenticated Student stream connects to Admin and the selected Teacher. Their Monitoring cards show the live screen; Admin Lab Monitoring shows one active occupancy card per account. Student logout or closing the Student Portal ends the session.

If Admin or Teacher is not listed, first confirm Admin is signed in, both machines share the same reachable LAN, the firewall rules are active, and client isolation is disabled. Different Wi-Fi networks do not receive the local broadcast discovery response.

## SDLC and Installation Lifecycle

1. **Planning:** Identify lab roles, the Admin/login server, Teacher stream host, student endpoints, network addresses, and required firewall ports.
2. **Requirements:** Confirm supported Windows machines, Python 3.11 build environment, camera/screen-capture needs, and account approval policies.
3. **Design:** Keep user/session/rule data on the server in SQLite; use authenticated Student-client sessions for lab occupancy; separate passive Admin occupancy cards from command-capable live monitoring cards.
4. **Implementation:** Maintain the role applications, schema, network protocol, blocklist editor, history filters, and installer sources in this repository.
5. **Verification:** Compile changed Python modules, exercise date-range logic, test account approval and blocklist propagation, and verify LAN discovery, lab occupancy, and screen streams on the target Wi-Fi.
6. **Deployment:** Build `CompHub-Setup.exe`, install the Server on the designated host, install Student on lab PCs, sign in to Admin first, and verify local discovery and firewall access.
7. **Operations and maintenance:** Back up `%ProgramData%\CompHub\scholarnet.db`, distribute tested installer updates, confirm active sessions and rule propagation after updates, and uninstall only after preserving the database if it must be retained.