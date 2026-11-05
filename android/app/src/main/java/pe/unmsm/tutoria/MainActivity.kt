package pe.unmsm.tutoria

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    private lateinit var base: EditText
    private lateinit var token: EditText
    private lateinit var rows: LinearLayout
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        title = "TutorIA · ${packageManager.getPackageInfo(packageName, 0).versionName}"
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        val padding = (16 * resources.displayMetrics.density).toInt()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
            isFocusableInTouchMode = true
        }
        fun add(view: android.view.View) {
            layout.addView(view, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ))
        }
        base = EditText(this).apply {
            id = R.id.base_url
            hint = "http://127.0.0.1:8000"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(true)
            setText("http://127.0.0.1:8000")
        }
        token = EditText(this).apply {
            id = R.id.mobile_token
            hint = "Token móvil (solo memoria)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setSingleLine(true)
            isSaveEnabled = false
        }
        rows = LinearLayout(this).apply { id = R.id.case_rows; orientation = LinearLayout.VERTICAL }
        add(TextView(this).apply { text = "Datos sintéticos · casos aprobados" })
        add(TextView(this).apply { id = R.id.base_url_label; text = "URL del servidor" })
        add(base)
        add(TextView(this).apply { text = "Por USB: mantén conectado el celular a la computadora." })
        add(TextView(this).apply { text = "Token móvil" })
        add(token)
        add(Button(this).apply { id = R.id.refresh; text = "Actualizar"; setOnClickListener { load() } })
        add(rows)
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            addView(layout, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ))
        })
        layout.requestFocus()
    }
    private fun request(path: String, done: (String) -> Unit) {
        val endpoint = base.text.toString().trimEnd('/') + path
        val credential = token.text.toString()
        if (credential.isBlank()) {
            Toast.makeText(this, "Introduce el token móvil", Toast.LENGTH_SHORT).show()
            return
        }
        Thread {
            try {
                val connection = URL(endpoint).openConnection() as HttpURLConnection
                val data = try {
                    connection.connectTimeout = 10000; connection.readTimeout = 10000
                    connection.setRequestProperty("Authorization", "Bearer $credential")
                    check(connection.responseCode == 200) { "HTTP ${connection.responseCode}" }
                    connection.inputStream.bufferedReader().use { it.readText() }
                } finally { connection.disconnect() }
                runOnUiThread {
                    if (!isDestroyed) {
                        try { done(data) }
                        catch (_: Exception) { Toast.makeText(this, "Respuesta del servidor inválida", Toast.LENGTH_LONG).show() }
                    }
                }
            } catch (e: Exception) {
                runOnUiThread { if (!isDestroyed) Toast.makeText(this, "No se pudo cargar: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }.start()
    }
    private fun load() = request("/cases") { body ->
        val data = JSONArray(body)
        rows.removeAllViews()
        if (data.length() == 0) rows.addView(TextView(this).apply { text = "Sin casos aprobados" })
        for (i in 0 until data.length()) {
            val item = data.getJSONObject(i)
            rows.addView(Button(this).apply {
                text = "${item.getString("student")} · riesgo ${"%.1f".format(item.getDouble("risk") * 100)}%"
                setOnClickListener {
                    request("/cases/${item.getInt("id")}") { detailBody ->
                        val detail = JSONObject(detailBody)
                        request("/cases/${item.getInt("id")}/history") { historyBody ->
                            val history = JSONArray(historyBody)
                            val academic = detail.optJSONObject("academic")
                            val text = StringBuilder()
                                .append("Lote: ${detail.getInt("batch")}\n")
                                .append("Probabilidad estimada: ${"%.1f".format(detail.getDouble("risk") * 100)}%\n")
                            if (academic != null) {
                                fun binary(name: String): String = if (!academic.has(name) || academic.isNull(name)) "Sin dato / no aplica" else if (academic.getInt(name) == 1) "Sí" else "No"
                                text.append("Periodo: ${academic.opt("periodo")}\n")
                                    .append("Asistencia (0–1): ${academic.opt("asistencia")}\n")
                                    .append("Promedio: ${academic.opt("promedio")}\n")
                                    .append("Créditos aprobados: ${academic.opt("creditos_aprobados")}\n")
                                    .append("Matrícula vigente: ${binary("matriculado")}\n")
                                    .append("Pagos al día: ${binary("pagos_al_dia")}\n")
                            }
                            text.append("\nSeguimiento:\n")
                            for (j in 0 until history.length()) {
                                val event = history.getJSONObject(j)
                                text.append("${event.getString("created")} · ${event.getString("action")}\n${event.getString("note")}\n\n")
                            }
                            AlertDialog.Builder(this@MainActivity).setTitle(item.getString("student"))
                                .setMessage(text.toString()).setPositiveButton("Cerrar", null).show()
                        }
                    }
                }
            })
        }
    }
}
