package pe.unmsm.tutoria

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.text.InputType
import android.widget.*
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    private lateinit var base: EditText
    private lateinit var token: EditText
    private lateinit var rows: LinearLayout
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24,24,24,24) }
        base = EditText(this).apply { hint = "URL del servidor"; setText("http://10.0.2.2:8000") }
        token = EditText(this).apply {
            hint = "Token móvil (solo memoria)"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSaveEnabled = false
        }
        rows = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        layout.addView(TextView(this).apply { text = "TutorIA · datos sintéticos · casos aprobados" })
        layout.addView(base); layout.addView(token)
        layout.addView(Button(this).apply { text = "Actualizar"; setOnClickListener { load() } })
        layout.addView(ScrollView(this).apply { addView(rows) })
        setContentView(layout)
    }
    private fun request(path: String, done: (JSONArray) -> Unit) {
        val endpoint = base.text.toString().trimEnd('/') + path
        val credential = token.text.toString()
        Thread {
            try {
                val connection = URL(endpoint).openConnection() as HttpURLConnection
                val data = try {
                    connection.connectTimeout = 10000; connection.readTimeout = 10000
                    connection.setRequestProperty("Authorization", "Bearer $credential")
                    check(connection.responseCode == 200) { "HTTP ${connection.responseCode}" }
                    connection.inputStream.bufferedReader().use { JSONArray(it.readText()) }
                } finally { connection.disconnect() }
                runOnUiThread { if (!isDestroyed) done(data) }
            } catch (e: Exception) {
                runOnUiThread { if (!isDestroyed) Toast.makeText(this, "No se pudo cargar: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }.start()
    }
    private fun load() = request("/cases") { data ->
        rows.removeAllViews()
        if (data.length() == 0) rows.addView(TextView(this).apply { text = "Sin casos aprobados" })
        for (i in 0 until data.length()) {
            val item = data.getJSONObject(i)
            rows.addView(Button(this).apply {
                text = "${item.getString("student")} · riesgo ${"%.1f".format(item.getDouble("risk") * 100)}%"
                setOnClickListener {
                    request("/cases/${item.getInt("id")}/history") { history ->
                        AlertDialog.Builder(this@MainActivity).setTitle(item.getString("student"))
                            .setMessage("Lote: ${item.getInt("batch")}\nEstado: ${item.getString("status")}\nHistorial:\n${history.toString(2)}")
                            .setPositiveButton("Cerrar", null).show()
                    }
                }
            })
        }
    }
}
