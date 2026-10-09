# DB definition

テーブルの文字コードは utf8mb4 にしてください。MySQL 5.7 など既定が latin1 のサーバでは、指定がないと日本語を入れられず `Incorrect string value` になります (出力の読み込みは MySQL 8.4、MySQL 5.7、MariaDB 11 で確認しています)。

銀行マスタ

```sql
CREATE TABLE `m_banks` (
  `bank_id` INT NOT NULL AUTO_INCREMENT COMMENT '銀行マスタ、banksのpk。ただし支店マスタとつなげるときはコレじゃなくてbank_codeを使うこと。',
  `bank_code` VARCHAR(45) NULL COMMENT '銀行コード。支店マスタとつなげるときはこれを使う。',
  `bank_name` VARCHAR(100) NULL COMMENT '銀行名。',
  `bank_name_kana` VARCHAR(100) NULL COMMENT '銀行名ｶﾅ',
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'INSERT日',
  `create_by` INT(11) NULL DEFAULT NULL COMMENT 'INSERT者',
  `update_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UPDATE日',
  `update_by` INT(11) NULL DEFAULT NULL COMMENT 'UPDATE者',
  PRIMARY KEY (`bank_id`)) DEFAULT CHARSET=utf8mb4;
```

支店マスタ

```sql
CREATE TABLE `m_bank_branches` (
  `bank_branch_id` int(11) NOT NULL AUTO_INCREMENT COMMENT '支店マスタ、bank_branchesのpk。ただし銀行マスタとつなげるときはbank_codeを使う。',
  `bank_code` varchar(45) DEFAULT NULL COMMENT '銀行コード。銀行マスタとつなげるときはこれを使う。',
  `branch_code` varchar(45) DEFAULT NULL COMMENT '支店コード。',
  `branch_name` varchar(100) DEFAULT NULL COMMENT '支店名。',
  `branch_name_kana` varchar(100) DEFAULT NULL COMMENT '支店名ｶﾅ',
  `create_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'INSERT日',
  `create_by` int(11) DEFAULT NULL COMMENT 'INSERT者',
  `update_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'UPDATE日',
  `update_by` int(11) DEFAULT NULL COMMENT 'UPDATE者',
  PRIMARY KEY (`bank_branch_id`)) DEFAULT CHARSET=utf8mb4;
```

読み込み後の確認用クエリです。最初の 2 つは実行時に表示された `銀行 1338 件、支店 31048 件` と一致し、重複のクエリは行を返さず、最後のクエリは 0 になるはずです。

```sql
SELECT COUNT(*) FROM m_banks;
SELECT COUNT(*) FROM m_bank_branches;
SELECT bank_code, COUNT(*) FROM m_banks GROUP BY bank_code HAVING COUNT(*) > 1;
SELECT bank_code, branch_code, COUNT(*) FROM m_bank_branches GROUP BY bank_code, branch_code HAVING COUNT(*) > 1;
SELECT COUNT(*) FROM m_bank_branches b LEFT JOIN m_banks k ON k.bank_code = b.bank_code WHERE k.bank_id IS NULL;
```
