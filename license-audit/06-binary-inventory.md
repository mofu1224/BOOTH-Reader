# バイナリ監査

監査日: 2026-10-02。判定: **BLOCKED**。

ネイティブ/ライブラリファイル: 391。全件のcontainer/path/size/hashはbinary-inventory.json。
exe/dll/pyd/lib等をアーカイブ内部まで列挙。分割.chunkはバイナリを隠すだけで配布義務をなくさない。
CPython・VC CRT・Node・Chrome・winldd・compiled wheelのlicense-to-file対応/静的リンク閉包は未確認。FFmpegは現行配布snapshotから除外。
OSのcmd/PowerShell/tar/whoami/icacls/dbghelp等は要求するがOSファイルをコピーして配布していない。
