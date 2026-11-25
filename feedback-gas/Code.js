// 소주도감 제보 수신: 사이트 제보 폼(POST) → 구글시트 한 줄 + 텔레그램 알림
// 시트 ID·chat_id는 setup()이 Script Properties에 저장

var PROPS = PropertiesService.getScriptProperties();
var HEADER = ['시각', '상태', '내용', '페이지', '메모'];

// 편집기에서 한 번 실행: 내 드라이브/프로젝트/소주 폴더에 시트 생성 + 봇 대화방 chat_id 저장
// 실행 전에 텔레그램에서 봇에게 아무 메시지나 보내 둘 것(getUpdates로 chat_id를 찾음)
function setup() {
  if (!PROPS.getProperty('SHEET_ID')) {
    var ss = SpreadsheetApp.create('📮 소주도감 제보');
    var sh = ss.getSheets()[0];
    sh.setName('제보');
    sh.appendRow(HEADER);
    sh.setFrozenRows(1);
    sh.getRange('1:1').setFontWeight('bold');
    sh.setColumnWidth(3, 480);
    sh.getRange('B2:B').setDataValidation(
      SpreadsheetApp.newDataValidation().requireValueInList(['새 제보', '반영', '보류', '반려']).build());
    var folder = findFolder_(['프로젝트', '소주']);
    if (folder) DriveApp.getFileById(ss.getId()).moveTo(folder);
    else Logger.log('소주 폴더를 못 찾아 내 드라이브 루트에 만듦');
    PROPS.setProperty('SHEET_ID', ss.getId());
  }
  var res = JSON.parse(UrlFetchApp.fetch(tgUrl_('getUpdates')).getContentText());
  var msgs = res.result.filter(function (u) { return u.message; });
  if (!msgs.length) throw new Error('봇에게 메시지를 먼저 보낸 뒤 다시 실행하세요');
  var chatId = String(msgs[msgs.length - 1].message.chat.id);
  PROPS.setProperty('CHAT_ID', chatId);
  sendTelegram_('소주도감 제보 알림 연결됨\n' + sheetUrl_());
  Logger.log('시트: ' + sheetUrl_() + ' / chat_id: ' + chatId);
}

function doPost(e) {
  var p = (e && e.parameter) || {};
  // honeypot: 사람 눈엔 안 보이는 칸이 채워져 있으면 봇으로 보고 성공처럼 응답만 함
  if (p.website) return json_({ ok: true });
  var message = String(p.message || '').trim().slice(0, 2000);
  if (!message) return json_({ ok: false });
  var page = String(p.page || '').slice(0, 200);
  var now = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm');
  // 수식 주입 방지: = + - @ 로 시작하면 앞에 ' 를 붙여 글자로 저장
  var safe = /^[=+\-@]/.test(message) ? "'" + message : message;
  SpreadsheetApp.openById(PROPS.getProperty('SHEET_ID')).getSheetByName('제보')
    .appendRow([now, '새 제보', safe, page, '']);
  try { sendTelegram_('📮 새 제보 (' + page + ')\n\n' + message + '\n\n' + sheetUrl_()); } catch (err) { Logger.log(err); }
  return json_({ ok: true });
}

function findFolder_(names) {
  var cur = DriveApp.getRootFolder();
  for (var i = 0; i < names.length; i++) {
    var it = cur.getFoldersByName(names[i]);
    if (!it.hasNext()) return null;
    cur = it.next();
  }
  return cur;
}

function sendTelegram_(text) {
  UrlFetchApp.fetch(tgUrl_('sendMessage'), {
    method: 'post',
    payload: { chat_id: PROPS.getProperty('CHAT_ID'), text: text, disable_web_page_preview: 'true' }
  });
}

function tgUrl_(method) { return 'https://api.telegram.org/bot' + TELEGRAM_TOKEN + '/' + method; }
function sheetUrl_() { return 'https://docs.google.com/spreadsheets/d/' + PROPS.getProperty('SHEET_ID'); }
function json_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }
