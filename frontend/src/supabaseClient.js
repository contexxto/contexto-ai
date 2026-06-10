import { createClient } from '@supabase/supabase-js'

// Variables públicas (van al bundle por diseño; la anon/publishable key es pública).
const url = import.meta.env.VITE_SUPABASE_URL
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY

// Si faltan las variables (ej. dev sin configurar), exportamos null y la app
// sigue funcionando en modo invitado sin romperse.
export const supabase = url && anon ? createClient(url, anon) : null
export const authEnabled = Boolean(supabase)
