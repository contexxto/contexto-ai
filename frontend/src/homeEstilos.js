// Estilos compartidos de la pantalla inicial vacía. Viven aquí y no en un componente para que
// el botón de menú (App.jsx) y la campana (Campana.jsx) no puedan desincronizarse: antes eran
// dos objetos escritos a mano que se llamaban «espejo» el uno al otro sin nada que los atara.

// Botón redondo translúcido del header mientras el chat está vacío.
export const BOTON_REDONDO = {
  width: 44, height: 44, padding: 0, borderRadius: '50%', alignItems: 'center', justifyContent: 'center',
  background: 'var(--home-row-bg)', border: '1px solid var(--home-row-border)',
}
