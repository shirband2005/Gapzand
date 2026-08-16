-- دیتابیس ربات مدیریت گروه دانشگاه زند شیراز
-- این فایل را در phpMyAdmin (یا مشابه) روی دیتابیسی که در config.py تعریف کردید اجرا کنید.

CREATE TABLE IF NOT EXISTS `groups` (
  `id`         BIGINT NOT NULL,
  `title`      VARCHAR(255) NULL,
  `settings`   JSON NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `users` (
  `id`         BIGINT NOT NULL,
  `first_name` VARCHAR(255) NULL,
  `username`   VARCHAR(255) NULL,
  `first_seen` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `group_members` (
  `group_id`     BIGINT NOT NULL,
  `user_id`      BIGINT NOT NULL,
  `warns`        INT NOT NULL DEFAULT 0,
  `flood_count`  INT NOT NULL DEFAULT 0,
  `flood_time`   INT NOT NULL DEFAULT 0,
  `is_verified`  TINYINT(1) NOT NULL DEFAULT 0,
  `invites`      INT NOT NULL DEFAULT 0,
  `joined_at`    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`group_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- در صورتی که این جدول از قبل روی دیتابیس شما وجود دارد (نصب قدیمی‌تر)، این خط را
-- جداگانه اجرا کنید تا ستون جدید «تعداد افرادی که هرکاربر به گروه اضافه کرده» ساخته شود:
-- ALTER TABLE `group_members` ADD COLUMN `invites` INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS `panel_pending` (
  `user_id`    BIGINT NOT NULL,
  `group_id`   BIGINT NOT NULL,
  `field`      VARCHAR(32) NOT NULL,
  `origin`     VARCHAR(32) NOT NULL,
  `message_id` BIGINT NOT NULL,
  `payload`    VARCHAR(255) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `force_join_channels` (
  `id`          INT NOT NULL AUTO_INCREMENT,
  `group_id`    BIGINT NOT NULL,
  `channel_id`  BIGINT NOT NULL,
  `username`    VARCHAR(255) NULL,
  `title`       VARCHAR(255) NULL,
  `invite_link` VARCHAR(255) NULL,
  `added_by`    BIGINT NOT NULL,
  `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_group_channel` (`group_id`, `channel_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `broadcasts` (
  `id`         INT NOT NULL AUTO_INCREMENT,
  `admin_id`   BIGINT NULL,
  `payload`    JSON NULL,
  `target`     ENUM('users','groups') NOT NULL DEFAULT 'groups',
  `total`      INT NOT NULL DEFAULT 0,
  `sent`       INT NOT NULL DEFAULT 0,
  `status`     ENUM('pending','running','done') NOT NULL DEFAULT 'pending',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
