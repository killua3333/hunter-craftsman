package com.huntercraftsman.mobile;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public class BuildIdentityTest {
    @Test
    public void debugBuildKeepsThePublishedIdentity() {
        assertEquals("com.huntercraftsman.mobile", BuildConfig.APPLICATION_ID);
        assertEquals("0.3.0", BuildConfig.VERSION_NAME);
    }
}
