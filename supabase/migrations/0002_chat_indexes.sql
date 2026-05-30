create index chat_messages_session_id_created_at on chat_messages (session_id, created_at);
create index chat_sessions_user_id_updated_at on chat_sessions (user_id, updated_at desc);
