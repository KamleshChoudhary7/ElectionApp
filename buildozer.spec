[app]
title = WarRoomPro
package.name = warroompro
package.domain = org.election.ward12
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,xlsx,pdf,ttf
version = 5.0.0

# Dependencies: Kivy, PyPDF, OpenPyXL, Pillow (for Image to PDF slip conversion)
requirements = python3,kivy==2.3.0,pypdf,openpyxl,et_xmlfile,sqlite3,fpdf2
orientation = portrait
fullscreen = 0

# Android 16 में क्रैश से बचने के लिए MANAGE_EXTERNAL_STORAGE नहीं है
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
p4a.branch = master
