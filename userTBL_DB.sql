CREATE DATABASE gmarketDB;

DROP DATABASE IF EXISTS gmarketDB;

show databases;

USE gmarketDB;

show tables;

CREATE TABLE userTBL (
    userID VARCHAR(20) NOT NULL,  -- 사용자 ID (필수 항목)
    password VARCHAR(15) NOT NULL,   -- 비밀번호 (필수 항목)
    name VARCHAR(10),   -- 이름
    gender ENUM('Female', 'Male') NOT NULL, -- 성별 (필수 항목)
    phoneNumber VARCHAR(11),  -- 전화번호
    email VARCHAR(40),   -- 이메일
    address VARCHAR(30), -- 주소
    PRIMARY KEY (userID, )  -- 주요 키로서 사용자 ID
);

CREATE TABLE userTBL (
    userID VARCHAR(20) NOT NULL PRIMARY KEY,  -- 사용자 ID (필수 항목)
    password VARCHAR(15) NOT NULL,   -- 비밀번호 (필수 항목)
    name VARCHAR(10),   -- 이름
    gender ENUM('Female', 'Male') NOT NULL, -- 성별 (필수 항목)
    phoneNumber VARCHAR(11),  -- 전화번호
    email VARCHAR(40),   -- 이메일
    address VARCHAR(30) -- 주소
);
CREATE TABLE userTBL (
    password VARCHAR(15) NOT NULL,   -- 비밀번호 (필수 항목)
    name VARCHAR(10),   -- 이름
    gender ENUM('Female', 'Male') NOT NULL, -- 성별 (필수 항목)
    phoneNumber VARCHAR(11),  -- 전화번호
    address VARCHAR(30), -- 주소
    PRIMARY KEY (name, phoneNumber)  -- 주요 키로서 사용자 ID
);

SHOW COLUMNS FROM userTBL;
 
desc userTBL;

-- insert추가

-- 1
INSERT INTO userTBL(userID, password, name, gender, phoneNumber, email, address)
 VALUES('dino', 'starEarth', '홍길동', 'Male', '01012345678', 'ysboo2@naver.com', '경기도 안산시 사동');

-- 2
INSERT INTO userTBL(userID, password,  name, gender, phoneNumber, email, address)
VALUES('tree', 'starMars', '이순신', 'Male', '01098546358', 'sea@naver.com', '여수시 오동도로 61');

 -- 3
INSERT INTO userTBL(userID, password,  name, gender, phoneNumber, email, address)
VALUES('sun', 'starSun',  '임꺽정', 'Male', '01089982577', 'Earth4@naver.com', '서울시 강남구 영동대로 513');
 

-- 4
INSERT INTO userTBL(userID, password,  name, gender, phoneNumber, email, address)
VALUES('Yu123', 'Yujeong1',  '김유정', 'Female', '01048275391', 'Yujeong@naver.com', '서울시 압구정동');
 
 -- 5
INSERT INTO userTBL(userID, password, name, gender, phoneNumber, email, address)
VALUES('Mun2', 'Munyeol2', '이문열', 'Male', '01059761428', 'Munyeol@naver.com', '수원시 팔달구');
 
-- 6 
INSERT INTO userTBL(userID, password, name, gender, phoneNumber, email, address)
VALUES('Dong', 'Dong-ri1234', '김동리', 'Male', '01031869570', 'Dong-ri@naver.com', '성남 분당구 서현동');

-- 7 
INSERT INTO userTBL(userID, password,  name, gender, phoneNumber, email, address)
VALUES('Lee346', 'LeeHyoseok23', '이효석', 'Male', '01093174682', 'LeeHyoseok@naver.com', '경남 창원시 마산동');

-- 8 
INSERT INTO userTBL(userID, password, name, gender, phoneNumber, email, address)
VALUES('Young',  'YoungdoLee', '이영도', 'Male', '01084693127', 'YoungdoLee@naver.com', '동해 천곡동');


-- 9
INSERT INTO userTBL(userID, password,  name, gender, phoneNumber, email, address)
VALUES('GongJiyoung1123', 'GongJiyoung1', '공지영', 'Female', '01062597418', 'GongJiyoung@naver.com', '강릉 교동');


-- 10
INSERT INTO userTBL(userID, password, name, gender, phoneNumber, email, address)
VALUES('Jang09', 'JangJeongil09', '장정일', 'Male', '01072684359', 'JangJeongil@naver.com', '부산 동구 초량동');

select * from userTBL;
delete from userTBL;



 DELETE FROM userTBL;  -- 테이블의 모든 행(row)을 삭제하는 쿼리
 DROP TABLE userTBL; -- userTBL삭제
 
 commit;
 
 select * from userTBL;
 
 -- 검색
 SELECT * FROM userTBL WHERE userID = 'dino';
 SELECT * FROM userTBL WHERE address LIKE '%여수시%';
 SELECT * FROM userTBL WHERE phoneNumber LIKE '%2577%';
 SELECT * FROM userTBL WHERE email = 'sea@naver.com';
 
 
 
-- 안전 모드 해제
SET SQL_SAFE_UPDATES=0; 

DELETE FROM userTBL WHERE address LIKE '%안산시%';
DELETE FROM userTBL WHERE address LIKE '%안산시%' AND userID = 'dino';

DELETE FROM userTBL WHERE userID = 'sea';

 -- 삭제
DELETE FROM userTBL WHERE userID = 'tree';


DELETE FROM userTBL WHERE email LIKE 'Earth%';

DELETE FROM userTBL WHERE email LIKE 'Earth%' AND userID = 'sun';

-- 안전 모드 실행은 1
SET SQL_SAFE_UPDATES=1; 


-- update
UPDATE userTBL
SET userID = 'dino99', password = 'starEarth99'
WHERE userID = 'dino';

UPDATE userTBL
SET gender = 'Female'
WHERE name = '이순신' AND userID = 'tree';


UPDATE userTBL
SET name = '임꺽순'
WHERE address LIKE '%서울시%';

UPDATE userTBL
SET name = '임꺽순'
WHERE address LIKE '%서울시%' AND userID = 'tree';


UPDATE userTBL
SET address = '제주도 애월읍'
WHERE phoneNumber LIKE '%1234%' And userID = 'dino';



UPDATE userTBL
SET address = '제주도 애월읍'
WHERE userID = 'tree';


UPDATE userTBL
SET address = '강원도 태백시', password = '0000'
WHERE userID = 'sun';



UPDATE userTBL
SET password = 'startMars98'
WHERE password = 'starMars' And userID='tree';

UPDATE userTBL
SET phoneNumber = '01099873333'
WHERE email = 'Earth4@naver.com' And userID='sun';


SELECT gender, COUNT(*) AS userCount
FROM userTBL
GROUP BY gender;
SELECT gender, COUNT(*)
FROM userTBL
GROUP BY gender;
SELECT gender, COUNT(*) as count
FROM userTBL
GROUP BY gender;


-- 서울이라는 키워드를 주소에서 포함한 사용자 수를 확인
SELECT address, COUNT(*) AS userCount
FROM userTBL
WHERE address LIKE '%서울%'
GROUP BY address;

SELECT address, COUNT(*) AS userCount
FROM userTBL
WHERE address LIKE '%서울%'
group by gender
;
SELECT gender, COUNT(*) AS userCount
FROM userTBL                              
WHERE address LIKE '%서울%'
group by gender
;
select * from userTBL;
SELECT address, COUNT(*) AS userCount
FROM userTBL
WHERE address LIKE '%서울%'
group by address
;

select * from userTBL;



select * from buyTBL;
select * from userTBL;

-- join 
-- INNER JOIN 양쪽 테이블에서 일치하는 행만 반환
 -- ON 절은 두 개의 테이블을 조인
SELECT userTBL.*, buyTBL.*
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID;

-- 두 테이블을 조인해서 userID와 Quantity 열만 보고 싶음
SELECT userTBL.userID, buyTBL.Quantity
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID;

 -- serID, ProductName, ProductPrice, address 열만 보고 싶음
SELECT userTBL.userID, buyTBL.ProductName, buyTBL.ProductPrice, userTBL.address
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID;

 -- userID, ProductName, ProductPrice, address 테이블에 열만 보고 싶음(테이블명을 한글로)
SELECT u.userID AS '사용자 ID', b.ProductName AS '상품 이름', b.ProductPrice AS '가격', u.address AS '주소'
FROM userTBL AS u
INNER JOIN buyTBL AS b ON u.userID = b.userID;

-- 물건을 가장 많이 구매한 상위 3명의 사용자를 찾기
SELECT userTBL.userID, SUM(buyTBL.Quantity) AS totalQuantity
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID
GROUP BY userTBL.userID
ORDER BY totalQuantity DESC
LIMIT 3;
-- 사고의 Step
SELECT u.userID, count(*) as count
FROM userTBL as u
-- 1
INNER JOIN buyTBL as b ON u.userID = b.userID
-- 2
GROUP BY u.userID
-- 3
order by count desc
;

-- 사고의 Step
SELECT *
FROM userTBL as u
INNER JOIN buyTBL as b ON u.userID = b.userID
;

SELECT userTBL.userID, buyTBL.ProductName, buyTBL.ProductPrice, userTBL.address
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID;
-- 뷰 생성 (데이터 보안 강화, 복잡한 쿼리 단순화, 재사용성 증가, 데이터 가상화, 관리 및 유지 보수 용이성을 제공)
-- 기존검색에서 첫줄만 추가 됨 
CREATE VIEW user_buy_view AS
SELECT userTBL.userID, buyTBL.ProductName, buyTBL.ProductPrice, userTBL.address
FROM userTBL
INNER JOIN buyTBL ON userTBL.userID = buyTBL.userID;

-- 뷰 보기
SELECT * FROM user_buy_view;

-- 뷰 삭제
DROP VIEW IF EXISTS user_buy_view;


CREATE TABLE femaleUsers (
	C1 varchar(30) not null primary key,
    c2 int
);
SELECT *
FROM userTBL
WHERE gender = 'Female';

-- 성별이 여성인 사용자만을 가진 새로운 테이블인 femaleUsers가 생성
CREATE TABLE femaleUsers AS
SELECT *
FROM userTBL
WHERE gender = 'Female';


show tables;

-- femaleUsers 테이블의 모든 레코드를 조회
SELECT * FROM femaleUsers;
SELECT * FROM user_buy_view;
SELECT * FROM userTBL;




-- 테이블에 이름을 변경
RENAME TABLE femaleUsers TO femaleUsers_member;

-- femaleUsers 테이블의 모든 레코드를 조회
SELECT * FROM femaleUsers_member;

drop table femaleUsers_member;

show tables;
