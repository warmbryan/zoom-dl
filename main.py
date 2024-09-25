import time
from datetime import datetime
import subprocess
import copy
import sys
import urllib.parse
from os import mkdir
from os.path import exists, join

import requests

from selenium import webdriver
from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
import selenium.webdriver.support.expected_conditions as EC

from selenium.webdriver import ChromeOptions

ZOOM_BASE_URL = ''
ZOOM_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0'

DOWNLOAD_PATH = 'downloads/'

# feel free to push requests, if you ever want to improve this.

# to operate the script
# python main.py "zoom recording url" "recording password"

def get_fileid_and_cookies(recordUrl, passcode):
    exports = {}

    options = ChromeOptions()

    # comment this out if you are having issues grabbing fileId and cookies, it should work fine.
    options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)

    driver.get(recordUrl)

    # wait slow
    waitS = WebDriverWait(driver, 60, 2)

    passcodeTextbox = waitS.until(EC.visibility_of_element_located((By.ID, "passcode")))
    passcodeTextbox.send_keys(passcode)

    time.sleep(1)

    passcodeBtn = waitS.until(EC.visibility_of_element_located((By.ID, "passcode_btn")))
    passcodeBtn.click()

    waitS.until(EC.visibility_of_element_located((By.CLASS_NAME, "player-view")))
    driver.implicitly_wait(10)

    # get fileId
    fileId = driver.execute_script('return window.__data__.fileId;')
    
    # goal 1 done
    exports['fileId'] = fileId

    print(f'fileId: {fileId}')
    try:
        cookies = driver.get_cookies()

        exportedCookies = []

        for cookie in cookies:
            
            # values
            cDomain = cookie.get('domain')
            cExpiry = cookie.get('expiry')
            cHttpOnly = cookie.get('httpOnly')
            cName: str = cookie.get('name')
            cPath = cookie.get('path')
            cSameSite = cookie.get('sameSite')
            cSecure = cookie.get('secure')
            cValue = cookie.get('value')

            print(f'domain: {cDomain}, expiry: {datetime.fromtimestamp(cExpiry) if cExpiry else None}, name: {cName}, value: {cValue}')

            # 25/09/24 - the required cookies should be sufficient
            if cName.startswith(('_zm', '__cf')) or len(cName) == 8:
                print('^ saved')
                exportedCookies.append(f'{cName}={cValue};')

            print('-' * 20)
        
        # goal 2 done
        exports['cookies'] = ' '.join(exportedCookies)

    except Exception:
        pass
    
    driver.close()
    driver.quit()

    return exports

# downloads any transcript/subtitles and returns a wget command for downloading of video
def get_recording(fileId: str, cookies: str, url: str):
    s = requests.Session()

    res = s.get(f'{ZOOM_BASE_URL}/nws/recording/1.0/play/info/{fileId}', headers={
        'User-Agent': ZOOM_USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Cookie': cookies
    })
    
    res.raise_for_status()
    recording = res.json()
    theRecording = recording.get('result')

    meet: dict = theRecording.get('meet')
    topic: str = meet.get('topic')

    fileStartTime = theRecording.get('fileStartTime')
    viewMp4Url = theRecording.get('viewMp4Url')

    recordingDate = datetime.fromtimestamp(fileStartTime / 1000)

    formattedDate = recordingDate.strftime('%d-%m-%Y')

    print(f'extracting {topic} @ {formattedDate}')

    requiredFileHeaders = {
        'User-Agent': ZOOM_USER_AGENT,
        'Referer': url,
        # 'Range': 'bytes=0-',
        'Connection': 'keep-alive',
        'Cookie': cookies
    }

    topic = topic.replace('\\', '-').replace('/', '-').replace('[', '(').replace(']', ')')
    output_file = f'{topic} {formattedDate}'

    # download transcript/subtitle
    try:
        tsPath = theRecording.get('transcriptUrl')
        if tsPath:
            tsUrl = f'{ZOOM_BASE_URL}{tsPath}'

            subtitleRes = requests.get(tsUrl, headers={
                'Cookie': cookies
            })

            subtitleRes.raise_for_status()

            with open(f'{DOWNLOAD_PATH}{output_file}.vtt', 'w') as subtitleFile:
                subtitleFile.write(bytes.decode(subtitleRes.content, 'utf-8'))
            
            print('transcript/subtitle downloaded')
        
    except requests.HTTPError:
        print('no transcript found')
        pass

    vHeaders = copy.deepcopy(requiredFileHeaders)
    vHeaders['Accept'] = 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5'

    headers = [f'--header "{header}: {vHeaders.get(header)}"' for header in vHeaders]

    headerArgs = ' '.join(headers)

    # generate wget command to download
    command = f'wget --no-check-certificate --method GET --timeout=0 {headerArgs} -O "{DOWNLOAD_PATH}{output_file}.mp4" "{viewMp4Url}"'

    return command

def download_zoom_recording():
    global ZOOM_BASE_URL

    parsedUrl = urllib.parse.urlparse(sys.argv[1])
    ZOOM_BASE_URL = f'{parsedUrl.scheme}://{parsedUrl.netloc}'

    info = get_fileid_and_cookies(sys.argv[1], sys.argv[2])

    command = get_recording(info['fileId'], info['cookies'], sys.argv[1])

    print('downloading...')

    subprocess.run(command, shell=True, check=True)

    print('done')

def check_file_path():
    dlPath = join(DOWNLOAD_PATH)

    if not exists(dlPath):
        mkdir(dlPath)

if __name__ == '__main__':
    check_file_path()

    download_zoom_recording()
