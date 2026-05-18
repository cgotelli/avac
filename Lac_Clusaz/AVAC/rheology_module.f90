module rheology_module
    !
    ! Module providing constitutive laws for basal friction.
    !
    ! Three laws are implemented:
    !
    !   - Coulomb:          tau = mu * rho * g * h * cos²(theta)
    !   - Voellmy:          tau = mu * rho * g * h * cos²(theta) + rho * g / xi * speed^2
    !   - Cohesive Voellmy: tau = C + mu * rho * g * h * cos²(theta) + rho * g / xi * speed^2
    !
    ! The functions return the kinematic stress tau/rho [m^2/s^2], which is
    ! the quantity directly needed for the momentum source term.
    !
    ! Explicit update in src2.f90 (after D-Claw, George & Iverson 2014):
    !   speed_new = max(0, speed - dt * tau/rho / h)
    !   (hu)^{n+1} = (hu/speed) * h * speed_new
    !   (hv)^{n+1} = (hv/speed) * h * speed_new
    !
    ! In 2D, theta is the local bed slope angle (rad), computed from the
    ! topography gradient in src2.f90.  The velocity magnitude (speed) is
    ! sqrt(u^2 + v^2); the direction is preserved by the explicit update.
    !
    implicit none

    ! Grid spacings for the current AMR level, set by b4step2.f90 before
    ! each Riemann solve and read by rpn2_geoclaw.f for the D-Claw static
    ! yield check.  Initialised to 1.0 (safe: check is conservative).
    real(kind=8) :: dx_avac = 1.d0
    real(kind=8) :: dy_avac = 1.d0

contains

    ! ------------------------------------------------------------------
    ! Coulomb friction: tau/rho = mu * g * h * cos²(theta)
    !
    ! Arguments:
    !   mu    - Coulomb friction coefficient (dimensionless)
    !   grav  - gravitational acceleration (m/s^2)
    !   h     - flow depth (m)
    !   theta - local bed slope angle (rad)
    ! ------------------------------------------------------------------
    function coulomb_tau(mu, grav, h, theta) result(tau_rho)
        implicit none
        real(kind=8), intent(in) :: mu, grav, h, theta
        real(kind=8) :: tau_rho

        tau_rho = mu * grav * h * dcos(theta)**2

    end function coulomb_tau


    ! ------------------------------------------------------------------
    ! Voellmy friction: tau/rho = mu * g * h * cos(theta) + g / xi * speed^2
    !
    ! Arguments:
    !   mu    - Coulomb friction coefficient (dimensionless)
    !   grav  - gravitational acceleration (m/s^2)
    !   h     - flow depth (m)
    !   theta - local bed slope angle (rad)
    !   xi    - Voellmy turbulence coefficient (m/s^2)
    !   speed - depth-averaged speed sqrt(u^2+v^2) (m/s)
    !
    ! Note: Coulomb is recovered in the limit xi -> infinity.
    ! ------------------------------------------------------------------
    function voellmy_tau(mu, grav, h, theta, xi, speed) result(tau_rho)
        implicit none
        real(kind=8), intent(in) :: mu, grav, h, theta, xi, speed
        real(kind=8) :: tau_rho

        tau_rho = mu * grav * h * dcos(theta)**2 + grav / xi * speed**2

    end function voellmy_tau


    ! ------------------------------------------------------------------
    ! Cohesive Voellmy friction:
    !   tau/rho = C/rho + mu * g * h * cos²(theta) + g / xi * speed^2
    !
    ! Arguments:
    !   mu    - Coulomb friction coefficient (dimensionless)
    !   grav  - gravitational acceleration (m/s^2)
    !   h     - flow depth (m)
    !   theta - local bed slope angle (rad)
    !   xi    - Voellmy turbulence coefficient (m/s^2)
    !   speed - depth-averaged speed sqrt(u^2+v^2) (m/s)
    !   C     - cohesion (Pa = kg/m/s^2)
    !   rho   - bulk density (kg/m^3)
    ! ------------------------------------------------------------------
    function cohesive_voellmy_tau(mu, grav, h, theta, xi, speed, C, rho) result(tau_rho)
        implicit none
        real(kind=8), intent(in) :: mu, grav, h, theta, xi, speed, C, rho
        real(kind=8) :: tau_rho

        tau_rho = C / rho + mu * grav * h * dcos(theta)**2 + grav / xi * speed**2

    end function cohesive_voellmy_tau

end module rheology_module
