package pe.unmsm.tutoria

import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Configurator
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ApprovalFlowTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val args = InstrumentationRegistry.getArguments()
    private val device = UiDevice.getInstance(instrumentation)
    private val baseUrl get() = args.getString("baseUrl") ?: error("Missing local API URL")

    private fun control(name: String): UiObject2 =
        device.wait(Until.findObject(By.res("pe.unmsm.tutoria", name)), 60000)
            ?: error("Control not found: $name")

    private fun request(path: String, role: String, body: JSONObject? = null): String {
        val connection = URL(baseUrl + path).openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 15000
            connection.readTimeout = 30000
            connection.setRequestProperty("Authorization", "Bearer " + args.getString(role))
            if (body != null) {
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            assertEquals("Local API request failed: $path", 200, connection.responseCode)
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally { connection.disconnect() }
    }

    @Test
    fun approvedCasesAndAcademicHistory() {
        // Avoid waiting for unrelated System UI animations in a software emulator.
        // Every expected screen and data value still has an explicit assertion.
        Configurator.getInstance().setWaitForIdleTimeout(0)
        val context = instrumentation.targetContext
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
            ?: error("Missing launch activity")
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        context.startActivity(launch)
        assertEquals("http://127.0.0.1:8000", control("base_url").text)
        assertEquals("URL del servidor", control("base_url_label").text)
        assertTrue("Server URL must be visible", control("base_url").visibleBounds.height() > 0)
        assertTrue("Mobile token must be visible", control("mobile_token").visibleBounds.height() > 0)
        control("mobile_token").click()
        device.pressBack()
        assertTrue("Server label hidden after closing keyboard", control("base_url_label").visibleBounds.height() > 0)
        val output = context.getExternalFilesDir(null) ?: error("Missing evidence directory")
        assertTrue(device.takeScreenshot(File(output, "tutoria-connection.png")))
        control("base_url").text = baseUrl
        control("mobile_token").text = args.getString("mobileToken") ?: error("Missing temporary mobile token")
        control("refresh").click()
        assertTrue("Pending cases must be hidden", device.wait(Until.hasObject(By.text("Sin casos aprobados")), 60000))

        val pending = JSONArray(request("/review", "reviewerToken"))
        assertEquals(3, pending.length())
        val note = "Seguimiento desde prueba Android"
        for (i in 0..1) {
            request("/review/${pending.getJSONObject(i).getInt("id")}", "reviewerToken",
                JSONObject().put("approve", true).put("note", note))
        }
        request("/review/${pending.getJSONObject(2).getInt("id")}", "reviewerToken",
            JSONObject().put("approve", false).put("note", "Caso rechazado en demostración"))
        val approved = JSONArray(request("/cases", "mobileToken"))
        assertEquals(2, approved.length())
        control("refresh").click()
        assertTrue("Approved cases did not render", device.wait(Until.hasObject(By.textContains(approved.getJSONObject(0).getString("student"))), 60000))
        assertTrue(device.wait(Until.hasObject(By.textContains(approved.getJSONObject(1).getString("student"))), 60000))
        val rows = device.findObjects(By.clazz("android.widget.Button"))
            .filter { it.text.orEmpty().contains("SYN-UI-") }.sortedBy { it.visibleBounds.top }
        assertEquals(2, rows.size)
        assertEquals(approved.getJSONObject(0).getString("student"), rows[0].text.split(" · ")[0])
        assertEquals(approved.getJSONObject(1).getString("student"), rows[1].text.split(" · ")[0])
        assertFalse("Rejected case leaked", device.hasObject(By.textContains(pending.getJSONObject(2).getString("student"))))
        rows[0].click()
        val detail = device.wait(Until.findObject(By.textContains("Matrícula vigente:")), 60000)
            ?: error("Academic detail did not render")
        assertTrue(detail.text.contains("Pagos al día:"))
        assertTrue(detail.text.contains(note))
        assertTrue(detail.text.contains("Asistencia"))
        assertTrue(detail.text.contains("Créditos aprobados"))
        assertTrue(device.takeScreenshot(File(output, "tutoria-smoke.png")))
        device.dumpWindowHierarchy(File(output, "tutoria-smoke.xml"))
    }
}
