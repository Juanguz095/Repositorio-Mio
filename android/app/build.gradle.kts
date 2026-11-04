plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "pe.unmsm.tutoria"
    compileSdk = 35
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    defaultConfig { applicationId = "pe.unmsm.tutoria"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "0.1"; testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner" }
}

dependencies {
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
    androidTestImplementation("junit:junit:4.13.2")
}
