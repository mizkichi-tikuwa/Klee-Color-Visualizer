# Klee Color Visualizer

本作品は、パウル・クレーの絵画に内在する色彩構造を、  音として体験可能な視聴覚システムである。

画像上の色をリアルタイムに解析し、PythonとMax/MSPを用いて音響パラメータへ変換することで、静的な絵画を時間的に展開される音として再提示する。

---
## 概要
・Python（pygame）で画像表示・UI・色解析・OSC送信を行います
・Max/MSPで音響生成と構造制御を行います
・マウスカーソルを鑑賞者の視点として扱い、カーソル位置の色が音へ変換されます

---

## フォルダ構成

```
Klee-Color-Visualizer/
├─ klee_main.py        ← 画像解析・UI制御・OSC送信（Python）
├─ klee_main.maxpat   ← 全体制御・色→音変換の中核パッチ
├─ inst_01.maxpat     ← 音響構造 1
├─ inst_02.maxpat     ← 音響構造 2
├─ Hue.txt            ← 自動生成（Hue 0–360 → 9段階の和音クラス）
├─ Value.txt          ← 自動生成（Value 0–99 → 音量用Velocity 1–128）
├─ modes2.txt         ← 和音構成用テキスト
├─ Image/
│ └─ back.png など    ← UI用画像素材
├─ Image_Main/
│ └─ main.jpg         ← 鑑賞対象となる作品画像
└─ README.md
```

---

## 動作環境

### Python
- Python 3.10.x  
  （3.10.0 にて動作確認済み）

### Pythonライブラリ
以下をインストールしてください。

```bash
pip install pygame python-osc
```
環境によっては pip ではなく pip3 が必要な場合があります。
```bash
pip3 install pygame python-osc
```

### Max
Max 8.x / 9.x
基本的には Max 標準オブジェクトのみで構成されています。
ただし環境によっては OSC-route が動作しない場合があるため、下記「トラブルシューティング」も参照してください。

---

## 起動手順

1. Maxを起動し、以下のパッチを開きます  
   - klee_main.maxpat  
   - （必要に応じて inst_01.maxpat, inst_02.maxpat）

2. ターミナルで、klee_main.py があるフォルダへ移動してから起動してください。

   ```bash
   cd /path/to/Klee-Color-Visualizer/
   python klee_main.py
   ```
   (必要によってpython3 klee_main.py)

3. 起動後の操作
   ・Pythonの画面がフルスクリーンで起動します
   ・「Start」ボタンを押して操作を開始してください
   ・「Exit」ボタンを押すとスタート画面に戻ります
   ・終了する場合は以下を使用してください。
      Esc キー または Exit ボタン

---

## 操作方法
Watch / Close
画像の色を読み取る ON / OFF

Sound
使用する音色（音響構造）を切り替えます
Sound1(音響構造1+2) / Sound2(音響構造1) / Sound3(音響構造2)


Delay
ディレイ（残響）の ON / OFF

マウスカーソル
鑑賞者の視点として扱われ、カーソル位置の色が音へ変換されます

### 色と音の対応関係（概要）
Hue（色相）→ 和音構成
Saturation（彩度）→ 音高
Value（明度）→ 音量

※ 本作品は、色を音へ一対一に変換することを目的とするものではなく、絵画に内在する色彩構造や要素間の関係性が、時間的に展開される音響構造として立ち上がることを目的に作成しています。

---

## 画像の差し替えについて
Image_Main フォルダ内の main.jpg を差し替えることで、表示する画像を変更できます
ファイル名は必ず main.jpg のままにしてください
推奨形式：JPEG（.jpg）

---

## OSC通信について
本システムでは、PythonからMaxへOSC通信を用いて制御を行います。
PythonとMaxは同一PC上での使用を想定しています。

使用しているOSCメッセージ
/text   : bang ←Hue.txt,Value.txt設定用
/hsv    : H(0–360), S(0–100), V(0–100)  
/TEMPO  : 0 / 1 ←Watch状態に連動、音の発音制御
/MODES  : 1 / 2 / 3 ←SoundMode切り替え
/delay  : 0 / 1 ←Delay On/Off

---
## トラブルシューティング
1) OSC-route が見つからない / 動かない（Max）
環境によっては、OSC-route の使用に CNMAT Externals のインストールが必要です。
Max → Package Manager を開く
CNMAT Externals を検索してインストール
過去にインストール済みの場合でも、Maxのバージョン変更等で認識されない場合があります。

2) python klee_main.py が動かない（Pythonのバージョン違い）
複数のPythonが入っている環境では、python が3.10ではない可能性があります。
その場合は、以下のようにバージョンを明示してください。
   ```bash
   python3.10 klee_main.py
   ```
（または環境に応じて python3）

3) 音は鳴るが「和音が変わらない」
起動後、音は鳴るが和音が変化しない場合、Max側の coll が空になっている可能性があります。
coll modes2 にデータが入っているかを確認してください。

---
## 備考
本パッチはMax標準のOSCオブジェクトを使用しており、
CNMAT等の追加パッケージは不要です
展示運用の安定性を考慮し、画像はアップロードではなく
フォルダ差し替え方式を採用しています