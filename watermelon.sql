-- 수박 DB 스키마를 만들어라
CREATE DATABASE watermelon;

-- 백틱을 사용하는 경우 (공백, 특수문자, 예약어 관련)
-- 공백이 포함된 이름
CREATE DATABASE `my watermelon db`;
-- 특수문자 포함
CREATE TABLE `order#1`;
-- 예약어인 경우 백틱 필요
CREATE TABLE `order`;

-- 수박 DB 스키마를 만들어라 
-- UTF-8mb4 문자 세트와 utf8mb4_unicode_ci 콜레이션을 사용하는 것이 일반적으로 가장 권장되는 방법
CREATE DATABASE watermelon CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 데이터베이스 확인
show databases;


-- 수박 DB를 사용하겠다
USE watermelon;

-- board 테이블이 있다면 삭제
DROP TABLE IF EXISTS BOARD;


-- board 테이블을 생성
-- ~~이런이런 조건(데이터 타입)으로 만들어라
CREATE TABLE board (
    BOARD_ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,  -- 게시물 ID (자동 증가)
    BOARD_TITLE VARCHAR(30),  -- 게시물 제목 (최대 30자)
    BOARD_CONTENT VARCHAR(500),  -- 게시물 내용 (최대 500자)
    REGISTER_ID VARCHAR(20),  -- 등록자 ID (최대 20자)
    REGISTER_DATE DATETIME DEFAULT CURRENT_TIMESTAMP,  -- 등록일자 (기본값: 현재 날짜와 시간)
    UPDATER_ID VARCHAR(20),  -- 수정자 ID (최대 20자)
    UPDATER_DATE DATETIME DEFAULT CURRENT_TIMESTAMP  -- 수정일자 (기본값: 현재 날짜와 시간)
);

-- board 테이블의 컬럼을 조회
SHOW COLUMNS FROM board;

-- 축약 문법
DESC board;

-- 테이블 이름 변경
RENAME TABLE board TO product;
DESC product;

-- 테이블 이름 확인하기
SHOW TABLES;

-- 원래대로 테이블 이름 복원
RENAME TABLE product TO board;

-- 열 이름과 타입, NOT NULL 제약조건 추가
ALTER TABLE board CHANGE BOARD_TITLE BOARD_TITLENAME VARCHAR(50) NOT NULL;

-- 열 수정 확인
DESC board;

-- 원래대로 열 이름 복원
ALTER TABLE board CHANGE BOARD_TITLENAME BOARD_TITLE VARCHAR(30);

-- 데이터 삽입
INSERT INTO BOARD (BOARD_TITLE, BOARD_CONTENT, REGISTER_ID) VALUES ('수박', '수박이 신선해요', '공룡');
INSERT INTO BOARD (BOARD_TITLE, BOARD_CONTENT, REGISTER_ID) VALUES ('수박2', '수박이 신선해요', '공룡');
INSERT INTO BOARD (BOARD_TITLE, BOARD_CONTENT, REGISTER_ID) VALUES ('수박5', '수박이 신선해요', '공룡5');

-- 영구적으로 저장 (MySql은 자동커밋 됨)
COMMIT;

-- 데이터 조회
SELECT * FROM BOARD;

-- 추가 데이터 삽입
INSERT INTO BOARD (BOARD_TITLE, BOARD_CONTENT, REGISTER_ID) VALUES ('수박이 안와요', '3일이나 기다렸어요', '사슴');
INSERT INTO BOARD (BOARD_TITLE, BOARD_CONTENT, REGISTER_ID) VALUES ('파손', '수박이 깨져서 왔어요', '토끼');

-- 특정 조건으로 데이터 검색
-- BOARD_ID가 1인 것 찾기
SELECT * FROM BOARD WHERE BOARD_ID = 1;

-- TITLE이 '파손'인 것 찾기
SELECT * FROM BOARD WHERE BOARD_TITLE = '파손';

-- REGISTER_ID에 '5'가 포함된 값 검색
SELECT * FROM BOARD WHERE REGISTER_ID LIKE '%5%';

-- REGISTER_ID가 '사슴'인 것 찾기
SELECT * FROM BOARD WHERE REGISTER_ID = '사슴';

-- BOARD_ID가 1부터 3까지인 레코드 선택
SELECT * FROM board WHERE BOARD_ID BETWEEN 1 AND 3;

-- 또는
SELECT * FROM board WHERE BOARD_ID >= 1 AND BOARD_ID <= 3;

-- BOARD_CONTENT가 '3'으로 시작하는 레코드 검색
SELECT * FROM board WHERE BOARD_CONTENT LIKE '3%';
SELECT * FROM board;
-- REGISTER_ID가 '공'으로 시작하는 레코드 검색
SELECT * FROM board WHERE REGISTER_ID LIKE '공%';
SELECT * FROM board WHERE REGISTER_ID LIKE '%날씨%';
SELECT * FROM board;

-- 데이터 업데이트
-- BOARD_ID가 1인 레코드 업데이트
UPDATE BOARD
SET BOARD_TITLE = '수박말고 생선', BOARD_CONTENT = '생선은 어디서 팔아요?'
WHERE BOARD_ID = 1;

-- BOARD_ID가 4인 레코드 업데이트
UPDATE BOARD
SET BOARD_TITLE = '수박말고 멜론', BOARD_CONTENT = '멜론도 먹고싶어요', REGISTER_ID='공룡할아버지'
WHERE BOARD_ID = 4;
SELECT * FROM board;
-- REGISTER_ID가 '공룡5'인 레코드 업데이트
UPDATE BOARD
SET BOARD_TITLE = '우왕', BOARD_CONTENT = '내수박은 어디에 있나?'
WHERE REGISTER_ID = '공룡5' AND BOARD_ID = 3;

-- 데이터 조회
SELECT * FROM BOARD;

-- 데이터 삭제
-- BOARD_ID가 1인 레코드 삭제
DELETE FROM BOARD WHERE BOARD_ID = 1;



-- 특정 조건으로 정확한 레코드 삭제
DELETE FROM BOARD WHERE REGISTER_ID = '사슴' AND BOARD_ID = 6;

-- BOARD_TITLE이 '파손'인 레코드 삭제
DELETE FROM BOARD WHERE BOARD_TITLE = '파손' AND BOARD_ID = 5;

-- WHERE 절 사용: WHERE 절에 키 컬럼을 추가하여 삭제
DELETE FROM BOARD WHERE BOARD_TITLE = '파손' AND BOARD_ID = 6;




-- 안전 모드 해제 (필요한 경우만 사용)
SET SQL_SAFE_UPDATES=1;   --  0이 off, 1이 on


-- REGISTER_ID가 '사슴'인 레코드 삭제
DELETE FROM BOARD WHERE REGISTER_ID = '사슴';

DELETE FROM BOARD WHERE BOARD_TITLE = '파손';



-- UPDATE 또는 DELETE 쿼리에 PRIMARY KEY 또는 INDEX가 설정된 열을 사용하여 안전 모드를 통과할 수 있다.
DELETE FROM BOARD WHERE REGISTER_ID = '사슴' AND BOARD_ID = 6;
DELETE FROM BOARD WHERE BOARD_TITLE = '파손' AND BOARD_ID = 6;

DELETE FROM BOARD WHERE BOARD_ID = 1;
DELETE FROM BOARD WHERE BOARD_ID = 3;
DELETE FROM BOARD WHERE BOARD_ID = 5;


-- BOARD_ID가 1과 2인 레코드 삭제
DELETE FROM BOARD WHERE BOARD_ID IN (1, 3, 5);

-- BOARD_ID가 1부터 8까지인 레코드 삭제 


-- board 테이블의 모든 데이터 삭제 (테이블 구조는 남기고 데이터만 삭제)
--  MySQL의 "Safe Update Mode"(안전 모드)에서 DELETE 또는 UPDATE 명령을 실행할 때 WHERE 절이 없으면 전체 데이터를 삭제하는 것을 방지하기 때문
-- 데이터를 한 줄씩 삭제함, 롤백이 가능함 (트랜잭션을 사용할 경우)
DELETE FROM board;


SET SQL_SAFE_UPDATES = 0;
DELETE FROM board;
SET SQL_SAFE_UPDATES = 1;  -- 작업 후 안전 모드 다시 켜기

-- WHERE 조건을 추가해서 삭제
DELETE FROM BOARD WHERE BOARD_ID BETWEEN 1 AND 8;


-- 데이터를 빠르게 한 번에 삭제함.
-- 롤백이 불가능함 (일부 DBMS에서 예외가 있음), AUTO_INCREMENT 값이 초기화됨
select * from board;

-- Watermelon DB를 삭제
DROP DATABASE IF EXISTS watermelon;

-- Watermelon DB를 삭제
DROP DATABASE watermelon;
