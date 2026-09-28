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

Allow the application ports through Windows Firewall on the server and lab network: TCP `5001`, `5050`, `9996`, `9997`, `9998`, and `9999`. Use stable IPv4 addresses for the Teacher stream host and Admin/login server. Keep the Student client installed and running on each lab PC; its authenticated login and stream connection automatically populate live monitoring and lab occupancy. The installer configures addresses but does not create firewall rules or discover arbitrary devices that do not run the client.

## SDLC and Installation Lifecycle

1. **Planning:** Identify lab roles, the Admin/login server, Teacher stream host, student endpoints, network addresses, and required firewall ports.
2. **Requirements:** Confirm supported Windows machines, Python 3.11 build environment, camera/screen-capture needs, and account approval policies.
3. **Design:** Keep user/session/rule data on the server in SQLite; use authenticated Student-client sessions for lab occupancy; separate passive Admin occupancy cards from command-capable live monitoring cards.
4. **Implementation:** Maintain the role applications, schema, network protocol, blocklist editor, history filters, and installer sources in this repository.
5. **Verification:** Compile changed Python modules, exercise date-range logic, test account approval and blocklist propagation, and verify lab occupancy and screen streams on the target LAN.
6. **Deployment:** Build `CompHub-Setup.exe`, install the Server on the designated host, install Student on lab PCs, enter the same network addresses in each wizard, and verify firewall access.
7. **Operations and maintenance:** Back up `%ProgramData%\CompHub\scholarnet.db`, distribute tested installer updates, confirm active sessions and rule propagation after updates, and uninstall only after preserving the database if it must be retained.