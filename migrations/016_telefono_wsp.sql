-- 016_telefono_wsp.sql
-- WhatsApp del corredor: habilita el deep-link wa.me (interesado -> corredor) en el
-- handoff. Vive en el PERFIL (no por inmueble): el corredor lo teclea una vez y aplica
-- a todo su inventario. Formato wa.me = codigo de pais + numero, sin '+' ni espacios
-- (ej. 593999123456). El backend tambien la autocrea en runtime (chat.ensure_perfil_wsp)
-- para no exigir correr este SQL a mano en el deploy; este archivo es el registro canonico.
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS telefono_wsp text;
