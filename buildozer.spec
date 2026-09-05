[app]
title = ElectionWarRoom
package.name = electionwarroom
package.domain = org.bhilwara.ward12
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db,xlsx,pdf,ttf
version = 4.0.0
requirements = python3,kivy==2.3.0,pypdf,openpyxl,et_xmlfile,sqlite3,pillow
orientation = portrait
fullscreen = 0
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
p4a.branch = master
