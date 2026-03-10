-- plntxt schema
-- SurrealDB 3.0

-- ============================================================
-- TABLES
-- ============================================================

-- user table
DEFINE TABLE user SCHEMAFULL;

DEFINE FIELD username ON user TYPE string;
DEFINE FIELD email ON user TYPE string ASSERT string::is_email($value);
DEFINE FIELD password ON user TYPE string;
DEFINE FIELD role ON user TYPE string DEFAULT 'user' ASSERT $value IN ['user', 'admin'];
DEFINE FIELD created_at ON user TYPE datetime DEFAULT time::now();

DEFINE INDEX unique_username ON user FIELDS username UNIQUE;
DEFINE INDEX unique_email ON user FIELDS email UNIQUE;

-- user permissions: users can read any profile, but only update/delete their own
DEFINE TABLE user SCHEMAFULL
    PERMISSIONS
        FOR select FULL
        FOR create NONE
        FOR update WHERE id = $auth.id
        FOR delete WHERE id = $auth.id;

-- post table
DEFINE TABLE post SCHEMAFULL
    PERMISSIONS
        FOR select WHERE published = true OR author = $auth.id
        FOR create WHERE $auth.id != NONE
        FOR update WHERE author = $auth.id OR type = 'wiki' OR $auth.role = 'admin'
        FOR delete WHERE author = $auth.id OR $auth.role = 'admin';

DEFINE FIELD type ON post TYPE string ASSERT $value IN ['blog', 'forum', 'wiki'];
DEFINE FIELD parent ON post TYPE option<record<post>>;
DEFINE FIELD title ON post TYPE option<string>;
DEFINE FIELD slug ON post TYPE option<string>;
DEFINE FIELD body ON post TYPE string;
DEFINE FIELD author ON post TYPE record<user> DEFAULT $auth.id;
DEFINE FIELD tags ON post TYPE array<string> DEFAULT [];
DEFINE FIELD published ON post TYPE bool DEFAULT true;
DEFINE FIELD created_at ON post TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON post TYPE datetime DEFAULT time::now() VALUE time::now();

DEFINE INDEX unique_slug ON post FIELDS type, slug UNIQUE;

-- revision table (wiki history)
DEFINE TABLE revision SCHEMAFULL
    PERMISSIONS
        FOR select FULL
        FOR create WHERE $auth.id != NONE
        FOR update NONE
        FOR delete WHERE $auth.role = 'admin';

DEFINE FIELD post ON revision TYPE record<post>;
DEFINE FIELD body ON revision TYPE string;
DEFINE FIELD author ON revision TYPE record<user> DEFAULT $auth.id;
DEFINE FIELD created_at ON revision TYPE datetime DEFAULT time::now();

-- tag table
DEFINE TABLE tag SCHEMAFULL
    PERMISSIONS
        FOR select FULL
        FOR create WHERE $auth.id != NONE
        FOR update WHERE $auth.role = 'admin'
        FOR delete WHERE $auth.role = 'admin';

DEFINE FIELD name ON tag TYPE string;
DEFINE FIELD type ON tag TYPE string DEFAULT 'label' ASSERT $value IN ['category', 'forum', 'label'];

DEFINE INDEX unique_tag_name ON tag FIELDS name UNIQUE;

-- ============================================================
-- AUTH ACCESS METHODS
-- ============================================================

-- default access (24h session)
DEFINE ACCESS default ON DATABASE TYPE RECORD
    SIGNUP (
        CREATE user CONTENT {
            username: $username,
            email: $email,
            password: crypto::argon2::generate($password),
            role: 'user',
            created_at: time::now()
        }
    )
    SIGNIN (
        SELECT * FROM user
        WHERE username = $username
            AND crypto::argon2::compare(password, $password)
    )
    DURATION FOR TOKEN 1h, FOR SESSION 24h;

-- remember-me access (30d session)
DEFINE ACCESS remember ON DATABASE TYPE RECORD
    SIGNUP (
        CREATE user CONTENT {
            username: $username,
            email: $email,
            password: crypto::argon2::generate($password),
            role: 'user',
            created_at: time::now()
        }
    )
    SIGNIN (
        SELECT * FROM user
        WHERE username = $username
            AND crypto::argon2::compare(password, $password)
    )
    DURATION FOR TOKEN 1h, FOR SESSION 30d;

-- ============================================================
-- FULL-TEXT SEARCH
-- ============================================================

DEFINE ANALYZER plntxt_search
    TOKENIZERS blank, class, punct
    FILTERS lowercase, snowball(english);

DEFINE INDEX post_title ON post
    FIELDS title FULLTEXT ANALYZER plntxt_search BM25;

DEFINE INDEX post_body ON post
    FIELDS body FULLTEXT ANALYZER plntxt_search BM25 HIGHLIGHTS;

-- ============================================================
-- FILE STORAGE (experimental)
-- ============================================================

DEFINE BUCKET uploads BACKEND "file:/data/uploads";
