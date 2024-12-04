from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from PIL import Image
import time

# مسار WebDriver الخاص بك (يجب تحديد المسار بشكل صحيح)
driver_path = 'chromedriver.exe'  # على سبيل المثال 'C:/path/to/chromedriver'

# إعداد ChromeOptions إذا كنت بحاجة إلى خيارات إضافية (مثل تشغيل المتصفح في الخلفية)
chrome_options = Options()
 # هذا الخيار لتشغيل المتصفح في الخلفية (اختياري)

# إعداد WebDriver باستخدام Service
service = Service(driver_path)
driver = webdriver.Chrome(service=service, options=chrome_options)

# فتح صفحة واتساب Web
driver.get("https://web.whatsapp.com/")

# الانتظار حتى يتم تحميل الصفحة وظهور رمز QR
time.sleep(12)  # يمكن تغيير الوقت حسب سرعة التحميل

# التقاط صورة للرمز QR
qr_element = driver.find_element(By.XPATH, '/html/body/div[1]/div/div/div[2]/div[2]/div[1]/div/div/div[2]/div[2]/div[1]/canvas')
location = qr_element.location
size = qr_element.size
driver.save_screenshot('whatsapp_screenshot.png')

# فتح الصورة الملتقطة
img = Image.open('whatsapp_screenshot.png')

# تحديد المنطقة التي تحتوي على رمز QR
left = location['x']
top = location['y']
right = left + size['width']
bottom = top + size['height']

# قص الصورة للحصول على الرمز QR
img.save('whatsapp_qr.png')
img.show()

# إغلاق المتصفح
driver.quit()
