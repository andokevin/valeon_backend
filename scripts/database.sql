-- =============================================
-- VALEON DATABASE SCHEMA
-- MySQL 8.0+ compatible
-- =============================================

CREATE DATABASE IF NOT EXISTS valeon CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE valeon;

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id       INT AUTO_INCREMENT PRIMARY KEY,
    subscription_name     VARCHAR(50) NOT NULL UNIQUE,
    subscription_price    FLOAT NOT NULL DEFAULT 0.0,
    subscription_duration INT NOT NULL DEFAULT 0,
    max_scans_per_day     INT NOT NULL DEFAULT 5,
    max_scans_per_month   INT NOT NULL DEFAULT 50,
    is_premium            TINYINT(1) NOT NULL DEFAULT 0,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

INSERT IGNORE INTO subscriptions VALUES
(1,'Free',   0,    0,  5,   50,   0, NOW()),
(2,'Basic',  4.99, 30, 20,  200,  0, NOW()),
(3,'Premium',9.99, 30, 999, 9999, 1, NOW());

CREATE TABLE IF NOT EXISTS users (
    user_id              INT AUTO_INCREMENT PRIMARY KEY,
    user_full_name       VARCHAR(100) NOT NULL,
    user_email           VARCHAR(100) NOT NULL UNIQUE,
    user_image           VARCHAR(500),
    user_subscription_id INT NOT NULL DEFAULT 1,
    is_active            TINYINT(1) NOT NULL DEFAULT 1,
    preferences          JSON,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email      (user_email),
    FOREIGN KEY (user_subscription_id) REFERENCES subscriptions(subscription_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_passwords (
    password_id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id                INT NOT NULL UNIQUE,
    password_hash          VARCHAR(255) NOT NULL,
    login_attempts         INT NOT NULL DEFAULT 0,
    locked_until           DATETIME,
    last_login             DATETIME,
    password_reset_token   VARCHAR(255),
    password_reset_expires DATETIME,
    created_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS contents (
    content_id             INT AUTO_INCREMENT PRIMARY KEY,
    content_type           VARCHAR(20) NOT NULL,
    content_title          VARCHAR(200) NOT NULL,
    content_original_title VARCHAR(200),
    content_description    TEXT,
    content_artist         VARCHAR(200),
    content_director       VARCHAR(200),
    content_cast           JSON,
    content_image          VARCHAR(500),
    content_backdrop       VARCHAR(500),
    content_release_date   VARCHAR(20),
    content_duration       INT,
    content_rating         FLOAT,
    content_url            VARCHAR(500),
    content_date           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    spotify_id             VARCHAR(100),
    tmdb_id                INT,
    imdb_id                VARCHAR(20),
    youtube_id             VARCHAR(100),
    justwatch_id           INT,
    content_metadata       JSON,
    INDEX idx_type         (content_type),
    INDEX idx_spotify      (spotify_id),
    INDEX idx_tmdb         (tmdb_id),
    INDEX idx_youtube      (youtube_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS external_links (
    link_id    INT AUTO_INCREMENT PRIMARY KEY,
    content_id INT NOT NULL,
    platform   VARCHAR(50) NOT NULL,
    link_url   VARCHAR(500) NOT NULL,
    embed_url  VARCHAR(500),
    FOREIGN KEY (content_id) REFERENCES contents(content_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS playlists (
    playlist_id          INT AUTO_INCREMENT PRIMARY KEY,
    playlist_name        VARCHAR(100) NOT NULL,
    playlist_description VARCHAR(500),
    playlist_image       VARCHAR(500),
    user_id              INT NOT NULL,
    is_public            TINYINT(1) NOT NULL DEFAULT 0,
    is_collaborative     TINYINT(1) NOT NULL DEFAULT 0,
    content_count        INT NOT NULL DEFAULT 0,
    playlist_metadata    JSON,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS playlist_contents (
    playlist_id INT NOT NULL,
    content_id  INT NOT NULL,
    added_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    position    INT NOT NULL DEFAULT 0,
    PRIMARY KEY (playlist_id, content_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(playlist_id) ON DELETE CASCADE,
    FOREIGN KEY (content_id)  REFERENCES contents(content_id)  ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS scans (
    scan_id               INT AUTO_INCREMENT PRIMARY KEY,
    scan_type             VARCHAR(20) NOT NULL,
    input_source          VARCHAR(20) NOT NULL DEFAULT 'file',
    file_path             VARCHAR(500),
    file_size             INT,
    processing_time       FLOAT,
    status                VARCHAR(20) NOT NULL DEFAULT 'pending',
    error                 VARCHAR(500),
    result                JSON,
    scan_date             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scan_user             INT NOT NULL,
    recognized_content_id INT,
    INDEX idx_scan_user   (scan_user),
    INDEX idx_scan_date   (scan_date),
    FOREIGN KEY (scan_user)             REFERENCES users(user_id)    ON DELETE CASCADE,
    FOREIGN KEY (recognized_content_id) REFERENCES contents(content_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS recognition_results (
    result_id       INT AUTO_INCREMENT PRIMARY KEY,
    scan_id         INT NOT NULL UNIQUE,
    raw_data        JSON,
    confidence      FLOAT,
    processing_time FLOAT,
    model_used      VARCHAR(50),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS favorites (
    favorite_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    content_id  INT NOT NULL,
    notes       VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_user_favorite (user_id, content_id),
    FOREIGN KEY (user_id)    REFERENCES users(user_id)    ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES contents(content_id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_activities (
    activity_id   INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    content_id    INT,
    metadata      JSON,
    ip_address    VARCHAR(50),
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_activity_user (user_id),
    INDEX idx_activity_date (created_at),
    FOREIGN KEY (user_id)    REFERENCES users(user_id)    ON DELETE CASCADE,
    FOREIGN KEY (content_id) REFERENCES contents(content_id) ON DELETE SET NULL
) ENGINE=InnoDB;
