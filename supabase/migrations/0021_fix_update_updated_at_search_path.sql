-- Fixes function_search_path_mutable security warning.
-- SET search_path = public pins the function's search_path so it cannot be
-- hijacked by a caller manipulating their session search_path.
-- Function body is unchanged; both triggers (chat_sessions, user_preferences) are unaffected.
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $function$
begin
    new.updated_at = now();
    return new;
end;
$function$;
