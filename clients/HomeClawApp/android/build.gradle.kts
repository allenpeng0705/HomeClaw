allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}
// Use Java 17 for all subprojects (plugins) to fix "Inconsistent JVM Target Compatibility" (Java 11 vs Kotlin 17).
// Run config immediately if project already evaluated; otherwise register afterEvaluate (avoids "Cannot run afterEvaluate when already evaluated").
fun configureJava17(project: org.gradle.api.Project) {
    // Set Android library compileOptions so Java tasks get 17 (AGP reads this for compile*JavaWithJavac).
    project.extensions.findByType(com.android.build.gradle.LibraryExtension::class.java)?.apply {
        compileOptions {
            sourceCompatibility = JavaVersion.VERSION_17
            targetCompatibility = JavaVersion.VERSION_17
        }
    }
    // Task-level Java compatibility (for non-Android or as fallback).
    project.tasks.withType(org.gradle.api.tasks.compile.JavaCompile::class.java).configureEach {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }
    // Kotlin: JVM 17 so it matches Java (avoids "Inconsistent JVM Target" with compile*Kotlin vs compile*JavaWithJavac).
    project.tasks.withType(org.jetbrains.kotlin.gradle.tasks.KotlinCompile::class.java).configureEach {
        compilerOptions.jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}
subprojects {
    val p = project
    if (p.state.executed) {
        configureJava17(p)
    } else {
        p.afterEvaluate { configureJava17(p) }
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
