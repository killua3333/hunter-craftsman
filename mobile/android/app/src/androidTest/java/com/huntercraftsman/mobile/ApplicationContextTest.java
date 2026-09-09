package com.huntercraftsman.mobile;

import static org.junit.Assert.assertEquals;

import android.content.Context;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class ApplicationContextTest {
    @Test
    public void applicationContextUsesTheExpectedIdentity() {
        Context appContext = InstrumentationRegistry.getInstrumentation().getTargetContext();

        assertEquals("com.huntercraftsman.mobile", appContext.getPackageName());
        assertEquals("猎人工坊", appContext.getString(R.string.app_name));
    }
}
