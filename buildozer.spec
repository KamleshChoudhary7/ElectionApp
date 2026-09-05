[app]
title = WarRoomPro
package.name = warroompro
package.domain = org.election.ward12
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,xlsx,pdf,ttf
version = 4.1.0
requirements = python3,kivy==2.3.0,pypdf,openpyxl,et_xmlfile,sqlite3,fpdf2
orientation = portrait
fullscreen = 0
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
p4a.branch = master
